import logging
from dataclasses import dataclass
from uuid import UUID
from app.clients import ResourceCatalogClient, ResourceCatalogClientError
from typing import Awaitable
from app.schemas import (
    AccessRequestRead,
    ApplyDecisionRequest,
    RequestOperation,
    RequestStatus,
    RequestTargetType,
    UserPermissionsRead,
)


@dataclass(frozen=True)
class ValidationResult:

    approved: bool
    rejection_reason: str | None = None

    @classmethod
    def approve(cls) -> "ValidationResult":

        return cls(approved=True)

    @classmethod
    def reject(cls, reason: str) -> "ValidationResult":

        return cls(approved=False, rejection_reason=reason)


class AccessRequestValidator:

    def __init__(
        self,
        *,
        resource_catalog_client: ResourceCatalogClient,
        logger: logging.Logger,
    ) -> None:

        self._client = resource_catalog_client
        self._logger = logger

    async def validate(self, request: AccessRequestRead) -> ValidationResult:

        self._logger.info(
            "Validating request: id=%s user=%s operation=%s target_type=%s target_id=%s",
            request.id, request.user_id, request.operation,
            request.target_type, request.target_id,
        )
        return await self._route_validation(request)


    async def _route_validation(
        self,
        request: AccessRequestRead,
    ) -> ValidationResult:

        operation = request.operation
        target_type = request.target_type

        if operation == RequestOperation.GRANT and target_type == RequestTargetType.ACCESS:
            return await self._validate_grant_access(request)

        if operation == RequestOperation.REVOKE and target_type == RequestTargetType.ACCESS:
            return await self._validate_revoke_access(request)

        if operation == RequestOperation.GRANT and target_type == RequestTargetType.RIGHT_GROUP:
            return await self._validate_grant_right_group(request)

        if operation == RequestOperation.REVOKE and target_type == RequestTargetType.RIGHT_GROUP:
            return await self._validate_revoke_right_group(request)

        self._logger.error(
            "Unknown operation combination: operation=%s target_type=%s",
            operation,
            target_type,
        )
        return ValidationResult.reject(
            f"Unsupported operation: {operation} {target_type}"
        )


    async def _validate_grant_access(
        self,
        request: AccessRequestRead,
    ) -> ValidationResult:

        if not await self._exists(self._client.get_access(request.target_id)):
            return ValidationResult.reject(
                f"Access {request.target_id} does not exist"
            )

        permissions = await self._client.get_user_permissions(request.user_id)

        conflict_reason = await self._check_access_conflicts_with_user_group(
            access_id=request.target_id,
            permissions=permissions,
        )
        if conflict_reason is not None:
            self._logger.info(
                "GRANT ACCESS rejected due to group conflict: "
                "user=%s access=%s reason=%s",
                request.user_id,
                request.target_id,
                conflict_reason,
            )
            return ValidationResult.reject(conflict_reason)

        self._logger.info(
            "GRANT ACCESS approved: user=%s access=%s",
            request.user_id,
            request.target_id,
        )
        return ValidationResult.approve()

    async def _validate_revoke_access(
        self,
        request: AccessRequestRead,
    ) -> ValidationResult:

        if not await self._exists(self._client.get_access(request.target_id)):
            return ValidationResult.reject(
                f"Access {request.target_id} does not exist"
            )

        self._logger.info(
            "REVOKE ACCESS approved: user=%s access=%s",
            request.user_id,
            request.target_id,
        )
        return ValidationResult.approve()

    async def _validate_grant_right_group(
        self,
        request: AccessRequestRead,
    ) -> ValidationResult:

        if not await self._exists(self._client.get_right_group(request.target_id)):
            return ValidationResult.reject(
                f"Right group {request.target_id} does not exist"
            )

        permissions = await self._client.get_user_permissions(request.user_id)

        group_conflict_reason = await self._check_group_vs_group_conflict(
            requested_group_id=request.target_id,
            permissions=permissions,
        )
        if group_conflict_reason is not None:
            self._logger.info(
                "GRANT RIGHT_GROUP rejected (group conflict): "
                "user=%s group=%s reason=%s",
                request.user_id,
                request.target_id,
                group_conflict_reason,
            )
            return ValidationResult.reject(group_conflict_reason)

        direct_access_conflict_reason = (
            await self._check_group_vs_direct_accesses_conflict(
                requested_group_id=request.target_id,
                permissions=permissions,
            )
        )
        if direct_access_conflict_reason is not None:
            self._logger.info(
                "GRANT RIGHT_GROUP rejected (direct access conflict): "
                "user=%s group=%s reason=%s",
                request.user_id,
                request.target_id,
                direct_access_conflict_reason,
            )
            return ValidationResult.reject(direct_access_conflict_reason)

        self._logger.info(
            "GRANT RIGHT_GROUP approved: user=%s group=%s",
            request.user_id,
            request.target_id,
        )
        return ValidationResult.approve()

    async def _validate_revoke_right_group(
        self,
        request: AccessRequestRead,
    ) -> ValidationResult:

        if not await self._exists(self._client.get_right_group(request.target_id)):
            return ValidationResult.reject(
                f"Right group {request.target_id} does not exist"
            )

        self._logger.info(
            "REVOKE RIGHT_GROUP approved: user=%s group=%s",
            request.user_id,
            request.target_id,
        )
        return ValidationResult.approve()

    async def _exists(self, coro: Awaitable[object]) -> bool:
        # Как альтернатива использовать два отдельных метода _entity_exists_access и _entity_exists_group
        try:
            await coro
            return True
        except ResourceCatalogClientError as exc:
            if exc.status_code == 404:
                return False
            raise


    async def _check_group_vs_group_conflict(
        self,
        *,
        requested_group_id: UUID,
        permissions: UserPermissionsRead,
    ) -> str | None:

        if permissions.right_group is None:
            return None

        current_group_id = permissions.right_group.id

        if current_group_id == requested_group_id:
            return None

        conflicts = await self._client.list_group_conflicts(requested_group_id)
        conflicting_ids = {c.conflicting_group_id for c in conflicts}

        if current_group_id in conflicting_ids:
            current_group_name = permissions.right_group.name
            return (
                f"Requested group conflicts with user's current group "
                f"'{current_group_name}'"
            )

        return None

    async def _check_group_vs_direct_accesses_conflict(
        self,
        *,
        requested_group_id: UUID,
        permissions: UserPermissionsRead,
    ) -> str | None:

        if not permissions.direct_access_ids:
            return None

        user_direct_access_ids = set(permissions.direct_access_ids)
        conflicts = await self._client.list_group_conflicts(requested_group_id)

        for conflict in conflicts:
            conflicting_group_id = conflict.conflicting_group_id

            group_accesses = await self._client.list_group_accesses(
                conflicting_group_id,
            )
            conflicting_access_ids = {a.id for a in group_accesses}

            overlap = user_direct_access_ids & conflicting_access_ids
            if overlap:
                return (
                    f"User has direct access from a group that conflicts "
                    f"with the requested group. "
                    f"Conflicting access ids: "
                    f"{', '.join(str(aid) for aid in overlap)}"
                )

        return None

    async def _check_access_conflicts_with_user_group(
        self,
        *,
        access_id: UUID,
        permissions: UserPermissionsRead,
    ) -> str | None:

        if permissions.right_group is None:
            return None

        current_group_id = permissions.right_group.id
        current_group_name = permissions.right_group.name

        conflicts = await self._client.list_group_conflicts(current_group_id)

        for conflict in conflicts:
            conflicting_group_id = conflict.conflicting_group_id

            group_accesses = await self._client.list_group_accesses(
                conflicting_group_id,
            )
            conflicting_access_ids = {a.id for a in group_accesses}

            if access_id in conflicting_access_ids:
                return (
                    f"Requested access belongs to a group that conflicts "
                    f"with user's current group '{current_group_name}'"
                )

        return None


def build_decision(result: ValidationResult) -> ApplyDecisionRequest:

    status = RequestStatus.APPROVED if result.approved else RequestStatus.REJECTED
    return ApplyDecisionRequest(
        status=status,
        rejection_reason=result.rejection_reason,
        modified_by="policy-engine",
    )