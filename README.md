# Access Control System

Три микросервиса для управления доступом: выдача и отзыв прав через заявки с асинхронной проверкой правил.

## Архитектура

```
Frontend
  → REST
Access Manager (порт 8001)
  → HTTP POST /internal/requests
Resource Catalog (порт 8003, PostgreSQL)
  → Kafka
Policy Engine (порт 8002)
  → HTTP POST /internal/requests/{id}/decision
Resource Catalog
```

## Запуск

```bash
docker compose up --build
docker exec resource-catalog alembic upgrade head
```

## Healthcheck

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

## API

Фронтенд общается только с Access Manager на `http://localhost:8001`.

```bash
POST /requests -- Подать заявку (202 + PENDING)
GET /requests/{id} -- Статус заявки
GET /users/{user_id}/requests -- История заявок пользователя
GET /users/{user_id}/permissions -- Текущие права пользователя
GET /resources/{resource_id}/accesses -- Доступы ресурса
```

### POST /requests

```json
{
  "user_id": "alice",
  "operation": "GRANT",
  "target_type": "ACCESS",
  "target_id": "uuid"
}
```

`operation`: `GRANT` или `REVOKE`
`target_type`: `ACCESS` или `RIGHT_GROUP`

Ответ — 202 с `status: PENDING`. Решение выносит Policy Engine асинхронно.
Опрашивай `GET /requests/{id}` пока статус не станет `APPROVED` или `REJECTED`.

### GET /users/{user_id}/permissions

```json
{
  "user_id": "alice",
  "right_group": { "id": "uuid", "name": "Developer", ... },
  "direct_accesses": [...],
  "effective_accesses": [...]
}
```

`effective_accesses` — прямые доступы + доступы из группы без дублей.

## Бизнес-правила

Policy Engine отклоняет заявку если:

- Target (Access или RightGroup) не существует
- Пользователь в Developer запрашивает доступ из Owner (конфликт)
- Пользователь в Developer запрашивает группу Owner (конфликт)
- У пользователя прямой доступ из Owner, запрашивает Developer (конфликт)

Конфликт симметричный: Developer ↔ Owner работает в обе стороны.

REVOKE всегда одобряется если target существует.