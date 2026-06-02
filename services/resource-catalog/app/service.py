from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (
    AccessModel,
    AccessRequestModel,
    ResourceModel,
    RightGroupAccessModel,
    RightGroupConflictModel,
    RightGroupModel,
    UserAccessModel,
    UserRightGroupModel,
)
from app.repository import ResourceCatalogRepository
from app.schemas import (
    AccessCreate,
    AccessRequestCreate,
    ApplyDecision,
    RequestOperation,
    RequestStatus,
    RequestTargetType,
    ResourceCreate,
    RightGroupCreate,
    UserPermissionsRead,
    AccessRead,
    RightGroupRead,
)


class CatalogError(Exception):

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EntityNotFoundError(CatalogError):
    """Raised when a requested entity does not exist in the registry"""


class EntityAlreadyExistsError(CatalogError):
    """Raised when a unique constraint would be violated"""


class InvalidCatalogOperationError(CatalogError):
    """Raised when an operation violates domain rules"""


def normalize_group_pair(
    first_group_id: UUID,
    second_group_id: UUID,
) -> tuple[UUID, UUID]:

    return tuple(sorted((first_group_id, second_group_id), key=str))


class ResourceCatalogService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = ResourceCatalogRepository(session)

    async def create_resource(self, payload: ResourceCreate) -> ResourceModel:

        try:
            resource = await self._repository.create_resource(
                name=payload.name,
                resource_type=payload.resource_type,
                description=payload.description,
            )
            await self._session.commit()
            return resource
        except IntegrityError as exc:
            await self._session.rollback()
            raise EntityAlreadyExistsError("Resource with this name already exists") from exc

    async def get_resource(self, resource_id: UUID) -> ResourceModel:

        resource = await self._repository.get_resource(resource_id)
        if resource is None:
            raise EntityNotFoundError("Resource was not found")
        return resource

    async def create_access(self, payload: AccessCreate) -> AccessModel:

        await self.get_resource(payload.resource_id)

        try:
            access = await self._repository.create_access(
                resource_id=payload.resource_id,
                name=payload.name,
                description=payload.description,
                metadata=payload.metadata,
                secret_ref=payload.secret_ref,
            )
            await self._session.commit()
            return access
        except IntegrityError as exc:
            await self._session.rollback()
            raise EntityAlreadyExistsError(
                "Access with this name already exists for the resource"
            ) from exc

    async def get_access(self, access_id: UUID) -> AccessModel:

        access = await self._repository.get_access(access_id)
        if access is None:
            raise EntityNotFoundError("Access was not found")
        return access

    async def list_resource_accesses(self, resource_id: UUID) -> list[AccessModel]:

        await self.get_resource(resource_id)
        return await self._repository.list_accesses_by_resource(resource_id)


    async def create_right_group(self, payload: RightGroupCreate) -> RightGroupModel:

        try:
            group = await self._repository.create_right_group(
                name=payload.name,
                description=payload.description,
            )
            await self._session.commit()
            return group
        except IntegrityError as exc:
            await self._session.rollback()
            raise EntityAlreadyExistsError("Right group with this name already exists") from exc

    async def get_right_group(self, group_id: UUID) -> RightGroupModel:

        group = await self._repository.get_right_group(group_id)
        if group is None:
            raise EntityNotFoundError("Right group was not found")
        return group

    async def add_access_to_group(
        self,
        *,
        group_id: UUID,
        access_id: UUID,
    ) -> RightGroupAccessModel:

        await self.get_right_group(group_id)
        await self.get_access(access_id)

        existing = await self._repository.get_group_access_relation(
            group_id=group_id,
            access_id=access_id,
        )
        if existing is not None:
            return existing

        relation = await self._repository.add_access_to_group(
            group_id=group_id,
            access_id=access_id,
        )
        await self._session.commit()
        return relation

    async def list_group_accesses(self, group_id: UUID) -> list[AccessModel]:

        await self.get_right_group(group_id)
        return await self._repository.list_group_accesses(group_id)

    async def list_access_groups(self, access_id: UUID) -> list[RightGroupModel]:

        await self.get_access(access_id)
        return await self._repository.list_access_groups(access_id)

    async def add_group_conflict(
        self,
        *,
        group_id: UUID,
        conflicting_group_id: UUID,
    ) -> RightGroupConflictModel:

        if group_id == conflicting_group_id:
            raise InvalidCatalogOperationError("Right group cannot conflict with itself")

        await self.get_right_group(group_id)
        await self.get_right_group(conflicting_group_id)

        normalized_a, normalized_b = normalize_group_pair(group_id, conflicting_group_id)

        existing = await self._repository.get_group_conflict(
            group_id=normalized_a,
            conflicting_group_id=normalized_b,
        )
        if existing is not None:
            return existing

        conflict = await self._repository.add_group_conflict(
            group_id=normalized_a,
            conflicting_group_id=normalized_b,
        )
        await self._session.commit()
        return conflict

    async def list_group_conflicts(self, group_id: UUID) -> list[RightGroupModel]:

        await self.get_right_group(group_id)
        return await self._repository.list_group_conflicts(group_id)

    async def create_access_request(
        self,
        payload: AccessRequestCreate,
    ) -> AccessRequestModel:

        request = await self._repository.create_access_request(
            user_id=payload.user_id,
            operation=payload.operation,
            target_type=payload.target_type,
            target_id=payload.target_id,
            status=RequestStatus.PENDING,
        )
        await self._session.commit()
        return request

    async def get_access_request(self, request_id: UUID) -> AccessRequestModel:

        request = await self._repository.get_access_request(request_id)
        if request is None:
            raise EntityNotFoundError("Access request was not found")
        return request

    async def list_user_requests(self, user_id: str) -> list[AccessRequestModel]:

        return await self._repository.list_user_requests(user_id)

    async def apply_decision(
        self,
        request_id: UUID,
        payload: ApplyDecision,
    ) -> AccessRequestModel:

        request = await self.get_access_request(request_id)
        self._validate_request_is_pending(request)

        await self._repository.update_request_decision(
            request,
            status=payload.status,
            rejection_reason=payload.rejection_reason,
            modified_by=payload.modified_by,
        )

        if payload.status == RequestStatus.APPROVED:
            await self._apply_approved_request(request, modified_by=payload.modified_by)

        await self._session.commit()
        return request

    def _validate_request_is_pending(self, request: AccessRequestModel) -> None:

        if request.status != RequestStatus.PENDING:
            raise InvalidCatalogOperationError(
                f"Cannot apply decision to request with status '{request.status}'. "
                "Only PENDING requests can be processed."
            )

    async def _apply_approved_request(
        self,
        request: AccessRequestModel,
        *,
        modified_by: str,
    ) -> None:

        operation = request.operation
        target_type = request.target_type

        if operation == RequestOperation.GRANT and target_type == RequestTargetType.ACCESS:
            await self._grant_access(request, modified_by=modified_by)

        elif operation == RequestOperation.REVOKE and target_type == RequestTargetType.ACCESS:
            await self._revoke_access(request, modified_by=modified_by)

        elif operation == RequestOperation.GRANT and target_type == RequestTargetType.RIGHT_GROUP:
            await self._grant_right_group(request, modified_by=modified_by)

        elif operation == RequestOperation.REVOKE and target_type == RequestTargetType.RIGHT_GROUP:
            await self._revoke_right_group(request, modified_by=modified_by)

        else:
            raise InvalidCatalogOperationError(
                f"Unsupported operation combination: {operation} + {target_type}"
            )

    async def _grant_access(
        self,
        request: AccessRequestModel,
        *,
        modified_by: str,
    ) -> None:

        existing = await self._repository.get_active_user_access(
            user_id=request.user_id,
            access_id=request.target_id,
        )
        if existing is not None:
            return

        await self._repository.create_user_access(
            user_id=request.user_id,
            access_id=request.target_id,
            modified_by=modified_by,
        )

    async def _revoke_access(
        self,
        request: AccessRequestModel,
        *,
        modified_by: str,
    ) -> None:

        existing = await self._repository.get_active_user_access(
            user_id=request.user_id,
            access_id=request.target_id,
        )
        if existing is None:
            return

        await self._repository.deactivate_user_access(existing, modified_by=modified_by)

    async def _grant_right_group(
        self,
        request: AccessRequestModel,
        *,
        modified_by: str,
    ) -> None:

        current_assignment = await self._repository.get_active_user_right_group(
            request.user_id,
        )

        if current_assignment is not None:
            if current_assignment.group_id == request.target_id:
                return

            await self._repository.deactivate_user_right_group(
                current_assignment,
                modified_by=modified_by,
            )

        await self._repository.create_user_right_group(
            user_id=request.user_id,
            group_id=request.target_id,
            modified_by=modified_by,
        )

    async def _revoke_right_group(
        self,
        request: AccessRequestModel,
        *,
        modified_by: str,
    ) -> None:

        current_assignment = await self._repository.get_active_user_right_group(
            request.user_id,
        )

        if current_assignment is None:
            return

        if current_assignment.group_id != request.target_id:
            raise InvalidCatalogOperationError(
                "User does not have the requested right group"
            )

        await self._repository.deactivate_user_right_group(
            current_assignment,
            modified_by=modified_by,
        )

    async def get_user_permissions(self, user_id: str) -> UserPermissionsRead:

        group_assignment = await self._repository.get_active_user_right_group_with_details(
            user_id,
        )
        direct_user_accesses = await self._repository.list_active_user_accesses_with_details(
            user_id,
        )

        direct_accesses = [
            AccessRead.model_validate(ua.access) for ua in direct_user_accesses
        ]

        group_accesses: list[AccessRead] = []
        right_group_read = None

        if group_assignment is not None:
            right_group_read = RightGroupRead.model_validate(group_assignment.group)
            group_accesses = [
                AccessRead.model_validate(rga.access)
                for rga in group_assignment.group.accesses
                if rga.access is not None
            ]

        effective_accesses = _merge_accesses_unique(direct_accesses, group_accesses)

        return UserPermissionsRead(
            user_id=user_id,
            right_group=right_group_read,
            direct_accesses=direct_accesses,
            effective_accesses=effective_accesses,
        )


def _merge_accesses_unique(
    direct: list[AccessRead],
    from_group: list[AccessRead],
) -> list[AccessRead]:

    seen: dict[UUID, AccessRead] = {}

    for access in direct:
        seen[access.id] = access

    for access in from_group:
        if access.id not in seen:
            seen[access.id] = access

    return list(seen.values())