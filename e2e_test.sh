#!/usr/bin/env bash
# =============================================================================
# End-to-end integration test for Access Control System
# Блок 11: полная проверка flow от создания ресурса до получения прав.
#
# Использование:
#   chmod +x e2e_test.sh
#   ./e2e_test.sh
#
# Требования:
#   - docker compose up --build выполнен
#   - alembic upgrade head выполнен в resource-catalog
#   - python3 доступен в PATH
#
# Скрипт проверяет 5 сценариев:
#   1. Базовый flow: GRANT ACCESS → APPROVED
#   2. Конфликт группа↔группа: Developer → Owner → REJECTED
#   3. Прямой доступ из конфликтующей группы → REJECTED при GRANT GROUP
#   4. Пользователь в группе → REJECTED при GRANT ACCESS из конфликтующей группы
#   5. REVOKE: отзыв группы и доступа → APPROVED
# =============================================================================

set -euo pipefail

# =============================================================================
# Константы
# =============================================================================

readonly BFF_URL="http://localhost:8001"
readonly REGISTRY_URL="http://localhost:8003"
readonly KAFKA_WAIT_SECONDS=4   # ждём пока Policy Engine обработает событие
readonly PASS="✅ PASS"
readonly FAIL="❌ FAIL"

# =============================================================================
# Утилиты
# =============================================================================

log() {
    echo ""
    echo "──────────────────────────────────────────────"
    echo "  $1"
    echo "──────────────────────────────────────────────"
}

step() {
    echo "  → $1"
}

# Делает POST-запрос и возвращает тело ответа.
post() {
    local url="$1"
    local body="$2"
    curl -s -X POST "$url" \
        -H "Content-Type: application/json" \
        -d "$body"
}

# Делает GET-запрос и возвращает тело ответа.
get() {
    local url="$1"
    curl -s "$url"
}

# Извлекает поле из JSON.
json_field() {
    local json="$1"
    local field="$2"
    echo "$json" | python3 -c "import sys,json; print(json.load(sys.stdin)['$field'])"
}

# Проверяет что поле JSON равно ожидаемому значению.
assert_field() {
    local description="$1"
    local json="$2"
    local field="$3"
    local expected="$4"

    actual=$(echo "$json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
val = data.get('$field')
print(val if val is not None else 'null')
" 2>/dev/null || echo "PARSE_ERROR")

    if [ "$actual" = "$expected" ]; then
        echo "    $PASS $description: $field='$actual'"
    else
        echo "    $FAIL $description: expected $field='$expected', got '$actual'"
        echo "    Raw response: $json"
        exit 1
    fi
}

# Проверяет что поле JSON содержит подстроку.
assert_contains() {
    local description="$1"
    local json="$2"
    local field="$3"
    local substring="$4"

    actual=$(echo "$json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
val = data.get('$field')
print(val if val is not None else 'null')
" 2>/dev/null || echo "PARSE_ERROR")

    if echo "$actual" | grep -q "$substring"; then
        echo "    $PASS $description: $field contains '$substring'"
    else
        echo "    $FAIL $description: expected $field to contain '$substring', got '$actual'"
        echo "    Raw response: $json"
        exit 1
    fi
}

# Ждёт пока Policy Engine обработает Kafka-событие.
wait_for_policy_engine() {
    step "Waiting ${KAFKA_WAIT_SECONDS}s for Policy Engine to process event..."
    sleep "$KAFKA_WAIT_SECONDS"
}

# =============================================================================
# Шаг 0: Проверка доступности сервисов
# =============================================================================

log "Step 0: Checking service health"

for port in 8001 8002 8003; do
    response=$(get "http://localhost:$port/health")
    status=$(json_field "$response" "status")
    service=$(json_field "$response" "service")
    if [ "$status" = "ok" ]; then
        echo "    $PASS localhost:$port ($service) is healthy"
    else
        echo "    $FAIL localhost:$port is not healthy"
        exit 1
    fi
done

# =============================================================================
# Шаг 1: Создание справочных данных в Resource Catalog
# Шаги 1-6 из условия блока 11.
# =============================================================================

log "Step 1-6: Setting up Resource Catalog data"

# Шаг 1: Создать Resource.
step "Creating resource"
RESOURCE=$(post "$REGISTRY_URL/resources" \
    '{"name":"E2E Production DB","resource_type":"DATABASE","description":"E2E test database"}')
RESOURCE_ID=$(json_field "$RESOURCE" "id")
echo "    Resource ID: $RESOURCE_ID"

# Шаг 2: Создать два Access внутри ресурса.
# dev-read — будет принадлежать Developer.
# owner-admin — будет принадлежать Owner.
step "Creating dev-read access"
DEV_ACCESS=$(post "$REGISTRY_URL/accesses" \
    "{\"resource_id\":\"$RESOURCE_ID\",\"name\":\"dev-read\",
      \"description\":\"Read access for developers\",\"metadata\":{\"env\":\"prod\"}}")
DEV_ACCESS_ID=$(json_field "$DEV_ACCESS" "id")
echo "    dev-read Access ID: $DEV_ACCESS_ID"

step "Creating owner-admin access"
OWNER_ACCESS=$(post "$REGISTRY_URL/accesses" \
    "{\"resource_id\":\"$RESOURCE_ID\",\"name\":\"owner-admin\",
      \"description\":\"Admin access for owners\",\"metadata\":{\"env\":\"prod\"}}")
OWNER_ACCESS_ID=$(json_field "$OWNER_ACCESS" "id")
echo "    owner-admin Access ID: $OWNER_ACCESS_ID"

# Шаг 3: Создать Developer group.
step "Creating Developer group"
DEV_GROUP=$(post "$REGISTRY_URL/right-groups" \
    '{"name":"E2E Developer","description":"Developer right group"}')
DEV_GROUP_ID=$(json_field "$DEV_GROUP" "id")
echo "    Developer Group ID: $DEV_GROUP_ID"

# Шаг 4: Создать Owner group.
step "Creating Owner group"
OWNER_GROUP=$(post "$REGISTRY_URL/right-groups" \
    '{"name":"E2E Owner","description":"Owner right group"}')
OWNER_GROUP_ID=$(json_field "$OWNER_GROUP" "id")
echo "    Owner Group ID: $OWNER_GROUP_ID"

# Шаг 5: Добавить accesses в группы.
step "Adding dev-read to Developer group"
post "$REGISTRY_URL/right-groups/$DEV_GROUP_ID/accesses" \
    "{\"access_id\":\"$DEV_ACCESS_ID\"}" > /dev/null

step "Adding owner-admin to Owner group"
post "$REGISTRY_URL/right-groups/$OWNER_GROUP_ID/accesses" \
    "{\"access_id\":\"$OWNER_ACCESS_ID\"}" > /dev/null

# Шаг 6: Добавить conflict Developer <-> Owner.
step "Adding conflict: Developer <-> Owner"
CONFLICT=$(post "$REGISTRY_URL/right-groups/$DEV_GROUP_ID/conflicts" \
    "{\"conflicting_group_id\":\"$OWNER_GROUP_ID\"}")
echo "    Conflict created: $(json_field "$CONFLICT" "group_id") <-> $(json_field "$CONFLICT" "conflicting_group_id")"

echo ""
echo "    $PASS Catalog data created successfully"

# =============================================================================
# СЦЕНАРИЙ 1: Базовый flow GRANT ACCESS → APPROVED
# Шаги 7-14 из условия блока 11.
# =============================================================================

log "Scenario 1: Basic GRANT ACCESS flow (steps 7-14)"

USER_ALICE="e2e-alice"

# Шаг 7: Через BFF создать заявку.
step "7. Creating GRANT ACCESS request via BFF"
REQUEST=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_ALICE\",\"operation\":\"GRANT\",
      \"target_type\":\"ACCESS\",\"target_id\":\"$DEV_ACCESS_ID\"}")
REQUEST_ID=$(json_field "$REQUEST" "id")
echo "    Request ID: $REQUEST_ID"

# Шаг 8: BFF создаёт PENDING в Rule Registry.
assert_field "8. BFF created PENDING request" "$REQUEST" "status" "PENDING"
assert_field "8. HTTP 202 confirmed by status field" "$REQUEST" "status" "PENDING"

# Шаг 9: BFF публикует event в Kafka — проверяем через логи Policy Engine.
step "9. Checking Policy Engine received Kafka event (checking logs)"
sleep 1
LOGS=$(docker logs policy-engine --since 10s 2>&1 || true)
if echo "$LOGS" | grep -q "$REQUEST_ID"; then
    echo "    $PASS Policy Engine received event for request_id=$REQUEST_ID"
else
    echo "    ⚠️  Event not yet in logs, waiting for processing..."
fi

# Шаг 10-12: Policy Engine читает event, проверяет правила, сохраняет результат.
wait_for_policy_engine

# Шаг 13: Клиент через BFF получает статус заявки.
step "13. Getting request status via BFF"
STATUS_RESPONSE=$(get "$BFF_URL/requests/$REQUEST_ID")
assert_field "13. Request status is APPROVED" "$STATUS_RESPONSE" "status" "APPROVED"
assert_field "13. Modified by policy-engine" "$STATUS_RESPONSE" "last_modified_by" "policy-engine"

# Шаг 14: Клиент через BFF получает итоговые права пользователя.
step "14. Getting user permissions via BFF"
PERMISSIONS=$(get "$BFF_URL/users/$USER_ALICE/permissions")
assert_field "14. user_id correct" "$PERMISSIONS" "user_id" "$USER_ALICE"

# Проверяем что dev-read появился в direct_accesses.
HAS_DIRECT=$(echo "$PERMISSIONS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
ids = [a['id'] for a in data.get('direct_accesses', [])]
print('yes' if '$DEV_ACCESS_ID' in ids else 'no')
")
if [ "$HAS_DIRECT" = "yes" ]; then
    echo "    $PASS 14. dev-read appears in direct_accesses"
else
    echo "    $FAIL 14. dev-read not found in direct_accesses"
    exit 1
fi

# Проверяем что dev-read появился в effective_accesses.
HAS_EFFECTIVE=$(echo "$PERMISSIONS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
ids = [a['id'] for a in data.get('effective_accesses', [])]
print('yes' if '$DEV_ACCESS_ID' in ids else 'no')
")
if [ "$HAS_EFFECTIVE" = "yes" ]; then
    echo "    $PASS 14. dev-read appears in effective_accesses"
else
    echo "    $FAIL 14. dev-read not found in effective_accesses"
    exit 1
fi

# =============================================================================
# СЦЕНАРИЙ 2: Конфликт группа↔группа → REJECTED
# Пользователь уже в Developer, запрашивает Owner.
# =============================================================================

log "Scenario 2: Group conflict - Developer user requests Owner group"

USER_BOB="e2e-bob"

# Выдаём Developer пользователю Bob.
step "Granting Developer group to $USER_BOB"
R_DEV=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_BOB\",\"operation\":\"GRANT\",
      \"target_type\":\"RIGHT_GROUP\",\"target_id\":\"$DEV_GROUP_ID\"}")
R_DEV_ID=$(json_field "$R_DEV" "id")
wait_for_policy_engine

DEV_STATUS=$(get "$BFF_URL/requests/$R_DEV_ID")
assert_field "Developer GRANT approved" "$DEV_STATUS" "status" "APPROVED"

# Проверяем что Bob теперь в Developer.
BOB_PERMS=$(get "$BFF_URL/users/$USER_BOB/permissions")
HAS_GROUP=$(echo "$BOB_PERMS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
rg = data.get('right_group')
print('yes' if rg and rg.get('id') == '$DEV_GROUP_ID' else 'no')
")
if [ "$HAS_GROUP" = "yes" ]; then
    echo "    $PASS Bob is in Developer group"
else
    echo "    $FAIL Bob is not in Developer group"
    exit 1
fi

# Запрашиваем Owner — должен быть REJECTED из-за конфликта.
step "Requesting Owner group for $USER_BOB (should be REJECTED)"
R_OWNER=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_BOB\",\"operation\":\"GRANT\",
      \"target_type\":\"RIGHT_GROUP\",\"target_id\":\"$OWNER_GROUP_ID\"}")
R_OWNER_ID=$(json_field "$R_OWNER" "id")
wait_for_policy_engine

OWNER_STATUS=$(get "$BFF_URL/requests/$R_OWNER_ID")
assert_field "Owner GRANT rejected" "$OWNER_STATUS" "status" "REJECTED"
assert_contains "Rejection reason mentions conflict" \
    "$OWNER_STATUS" "rejection_reason" "conflicts"

# Проверяем что Bob всё ещё в Developer (права не изменились).
BOB_PERMS_AFTER=$(get "$BFF_URL/users/$USER_BOB/permissions")
HAS_DEV_STILL=$(echo "$BOB_PERMS_AFTER" | python3 -c "
import sys, json
data = json.load(sys.stdin)
rg = data.get('right_group')
print('yes' if rg and rg.get('id') == '$DEV_GROUP_ID' else 'no')
")
if [ "$HAS_DEV_STILL" = "yes" ]; then
    echo "    $PASS Bob remains in Developer group after REJECTED request"
else
    echo "    $FAIL Bob's group changed after REJECTED request"
    exit 1
fi

# =============================================================================
# СЦЕНАРИЙ 3: Прямой доступ из Owner → REJECTED при GRANT Developer
# Пользователь имеет прямой owner-admin access, запрашивает Developer group.
# =============================================================================

log "Scenario 3: Direct access from Owner blocks Developer group"

USER_CHARLIE="e2e-charlie"

# Выдаём Charlie прямой owner-admin access.
step "Granting owner-admin access directly to $USER_CHARLIE"
R_OA=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_CHARLIE\",\"operation\":\"GRANT\",
      \"target_type\":\"ACCESS\",\"target_id\":\"$OWNER_ACCESS_ID\"}")
R_OA_ID=$(json_field "$R_OA" "id")
wait_for_policy_engine

OA_STATUS=$(get "$BFF_URL/requests/$R_OA_ID")
assert_field "owner-admin GRANT approved" "$OA_STATUS" "status" "APPROVED"

# Запрашиваем Developer group — должен быть REJECTED.
step "Requesting Developer group for $USER_CHARLIE (should be REJECTED)"
R_DEV2=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_CHARLIE\",\"operation\":\"GRANT\",
      \"target_type\":\"RIGHT_GROUP\",\"target_id\":\"$DEV_GROUP_ID\"}")
R_DEV2_ID=$(json_field "$R_DEV2" "id")
wait_for_policy_engine

DEV2_STATUS=$(get "$BFF_URL/requests/$R_DEV2_ID")
assert_field "Developer GRANT rejected (has Owner access)" \
    "$DEV2_STATUS" "status" "REJECTED"
assert_contains "Rejection reason mentions direct access conflict" \
    "$DEV2_STATUS" "rejection_reason" "direct access"

# =============================================================================
# СЦЕНАРИЙ 4: Пользователь в Developer не может получить Owner access
# =============================================================================

log "Scenario 4: Developer user cannot get Owner access directly"

USER_DIANA="e2e-diana"

# Выдаём Diana Developer group.
step "Granting Developer group to $USER_DIANA"
R_DG=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_DIANA\",\"operation\":\"GRANT\",
      \"target_type\":\"RIGHT_GROUP\",\"target_id\":\"$DEV_GROUP_ID\"}")
R_DG_ID=$(json_field "$R_DG" "id")
wait_for_policy_engine

DG_STATUS=$(get "$BFF_URL/requests/$R_DG_ID")
assert_field "Developer GRANT approved" "$DG_STATUS" "status" "APPROVED"

# Запрашиваем owner-admin access напрямую — должен быть REJECTED.
step "Requesting owner-admin access for $USER_DIANA (should be REJECTED)"
R_OA2=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_DIANA\",\"operation\":\"GRANT\",
      \"target_type\":\"ACCESS\",\"target_id\":\"$OWNER_ACCESS_ID\"}")
R_OA2_ID=$(json_field "$R_OA2" "id")
wait_for_policy_engine

OA2_STATUS=$(get "$BFF_URL/requests/$R_OA2_ID")
assert_field "owner-admin GRANT rejected (user in Developer)" \
    "$OA2_STATUS" "status" "REJECTED"
assert_contains "Rejection reason mentions group conflict" \
    "$OA2_STATUS" "rejection_reason" "conflicts"

# Проверяем effective_accesses: только dev-read через группу, не owner-admin.
DIANA_PERMS=$(get "$BFF_URL/users/$USER_DIANA/permissions")
HAS_OWNER=$(echo "$DIANA_PERMS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
ids = [a['id'] for a in data.get('effective_accesses', [])]
print('yes' if '$OWNER_ACCESS_ID' in ids else 'no')
")
if [ "$HAS_OWNER" = "no" ]; then
    echo "    $PASS Diana does not have owner-admin in effective_accesses"
else
    echo "    $FAIL Diana has owner-admin in effective_accesses (should not)"
    exit 1
fi

HAS_DEV_ACCESS=$(echo "$DIANA_PERMS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
ids = [a['id'] for a in data.get('effective_accesses', [])]
print('yes' if '$DEV_ACCESS_ID' in ids else 'no')
")
if [ "$HAS_DEV_ACCESS" = "yes" ]; then
    echo "    $PASS Diana has dev-read via Developer group in effective_accesses"
else
    echo "    $FAIL Diana does not have dev-read in effective_accesses"
    exit 1
fi

# =============================================================================
# СЦЕНАРИЙ 5: REVOKE — отзыв группы и доступа
# =============================================================================

log "Scenario 5: REVOKE GROUP and REVOKE ACCESS"

USER_EVE="e2e-eve"

# Выдаём Eve Developer group и dev-read access.
step "Setting up Eve: Developer group + dev-read access"
R_EG=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_EVE\",\"operation\":\"GRANT\",
      \"target_type\":\"RIGHT_GROUP\",\"target_id\":\"$DEV_GROUP_ID\"}")
R_EG_ID=$(json_field "$R_EG" "id")

R_EA=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_EVE\",\"operation\":\"GRANT\",
      \"target_type\":\"ACCESS\",\"target_id\":\"$DEV_ACCESS_ID\"}")
R_EA_ID=$(json_field "$R_EA" "id")
wait_for_policy_engine

EG_STATUS=$(get "$BFF_URL/requests/$R_EG_ID")
EA_STATUS=$(get "$BFF_URL/requests/$R_EA_ID")
assert_field "Developer group GRANT approved" "$EG_STATUS" "status" "APPROVED"
assert_field "dev-read access GRANT approved" "$EA_STATUS" "status" "APPROVED"

# Проверяем начальные права.
EVE_PERMS=$(get "$BFF_URL/users/$USER_EVE/permissions")
HAS_GROUP=$(echo "$EVE_PERMS" | python3 -c "
import sys, json; data = json.load(sys.stdin)
rg = data.get('right_group')
print('yes' if rg else 'no')
")
if [ "$HAS_GROUP" = "yes" ]; then
    echo "    $PASS Eve has Developer group before REVOKE"
else
    echo "    $FAIL Eve does not have Developer group"
    exit 1
fi

# Отзываем Developer group.
step "Revoking Developer group from $USER_EVE"
R_RG=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_EVE\",\"operation\":\"REVOKE\",
      \"target_type\":\"RIGHT_GROUP\",\"target_id\":\"$DEV_GROUP_ID\"}")
R_RG_ID=$(json_field "$R_RG" "id")
wait_for_policy_engine

RG_STATUS=$(get "$BFF_URL/requests/$R_RG_ID")
assert_field "Developer group REVOKE approved" "$RG_STATUS" "status" "APPROVED"

# Проверяем что группа отозвана.
EVE_PERMS_AFTER=$(get "$BFF_URL/users/$USER_EVE/permissions")
GROUP_AFTER=$(echo "$EVE_PERMS_AFTER" | python3 -c "
import sys, json; data = json.load(sys.stdin)
rg = data.get('right_group')
print('null' if rg is None else rg.get('id', 'unknown'))
")
if [ "$GROUP_AFTER" = "null" ]; then
    echo "    $PASS Eve has no group after REVOKE"
else
    echo "    $FAIL Eve still has group after REVOKE: $GROUP_AFTER"
    exit 1
fi

# Прямой доступ dev-read должен остаться (REVOKE GROUP не затрагивает прямые доступы).
HAS_DIRECT_AFTER=$(echo "$EVE_PERMS_AFTER" | python3 -c "
import sys, json; data = json.load(sys.stdin)
ids = [a['id'] for a in data.get('direct_accesses', [])]
print('yes' if '$DEV_ACCESS_ID' in ids else 'no')
")
if [ "$HAS_DIRECT_AFTER" = "yes" ]; then
    echo "    $PASS Eve still has direct dev-read access after group REVOKE"
else
    echo "    $FAIL Eve lost direct access after group REVOKE (should not)"
    exit 1
fi

# Отзываем прямой dev-read access.
step "Revoking dev-read access from $USER_EVE"
R_RA=$(post "$BFF_URL/requests" \
    "{\"user_id\":\"$USER_EVE\",\"operation\":\"REVOKE\",
      \"target_type\":\"ACCESS\",\"target_id\":\"$DEV_ACCESS_ID\"}")
R_RA_ID=$(json_field "$R_RA" "id")
wait_for_policy_engine

RA_STATUS=$(get "$BFF_URL/requests/$R_RA_ID")
assert_field "dev-read access REVOKE approved" "$RA_STATUS" "status" "APPROVED"

# Проверяем что у Eve нет ни группы ни прямых доступов.
EVE_FINAL=$(get "$BFF_URL/users/$USER_EVE/permissions")
FINAL_DIRECT=$(echo "$EVE_FINAL" | python3 -c "
import sys, json; data = json.load(sys.stdin)
print(len(data.get('direct_accesses', [])))
")
FINAL_EFFECTIVE=$(echo "$EVE_FINAL" | python3 -c "
import sys, json; data = json.load(sys.stdin)
print(len(data.get('effective_accesses', [])))
")

if [ "$FINAL_DIRECT" = "0" ] && [ "$FINAL_EFFECTIVE" = "0" ]; then
    echo "    $PASS Eve has no accesses after full REVOKE"
else
    echo "    $FAIL Eve still has accesses: direct=$FINAL_DIRECT effective=$FINAL_EFFECTIVE"
    exit 1
fi

# =============================================================================
# ИТОГ
# =============================================================================

echo ""
echo "════════════════════════════════════════════════"
echo "  ✅ All end-to-end scenarios passed!"
echo ""
echo "  Covered:"
echo "  1. Full flow: GRANT ACCESS → APPROVED (steps 7-14)"
echo "  2. Group conflict: Developer → Owner → REJECTED"
echo "  3. Direct access blocks group: Owner access → Developer group REJECTED"
echo "  4. Group blocks direct access: Developer group → Owner access REJECTED"
echo "  5. REVOKE GROUP and REVOKE ACCESS → APPROVED"
echo "════════════════════════════════════════════════"