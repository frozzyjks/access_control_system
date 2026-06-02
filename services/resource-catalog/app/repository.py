from uuid import UUID
from sqlalchemy import or_, select
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
    utc_now,
)


class ResourceCatalogRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_resource(
        self,
        *,
        name: str,
        resource_type: str,
        description: str | None,
    ) -> ResourceModel:

        resource = ResourceModel(
            name=name,
            resource_type=resource_type,
            description=description,
        )
        self._session.add(resource)
        await self._session.flush()
        return resource

    async def get_resource(self, resource_id: UUID) -> ResourceModel | None:

        return await self._session.get(ResourceModel, resource_id)

    async def create_access(
        self,
        *,
        resource_id: UUID,
        name: str,
        description: str | None,
        metadata: dict,
        secret_ref: str | None,
    ) -> AccessModel:

        access = AccessModel(
            resource_id=resource_id,
            name=name,
            description=description,
            metadata_=metadata,
            secret_ref=secret_ref,
        )
        self._session.add(access)
        await self._session.flush()
        return access

    async def get_access(self, access_id: UUID) -> AccessModel | None:

        return await self._session.get(AccessModel, access_id)

    async def list_accesses_by_resource(self, resource_id: UUID) -> list[AccessModel]:

        result = await self._session.scalars(
            select(AccessModel)
            .where(AccessModel.resource_id == resource_id)
            .order_by(AccessModel.name)
        )
        return list(result)

    async def create_right_group(
        self,
        *,
        name: str,
        description: str | None,
    ) -> RightGroupModel:

        group = RightGroupModel(name=name, description=description)
        self._session.add(group)
        await self._session.flush()
        return group

    async def get_right_group(self, group_id: UUID) -> RightGroupModel | None:

        return await self._session.get(RightGroupModel, group_id)

    async def add_access_to_group(
        self,
        *,
        group_id: UUID,
        access_id: UUID,
    ) -> RightGroupAccessModel:

        relation = RightGroupAccessModel(group_id=group_id, access_id=access_id)
        self._session.add(relation)
        await self._session.flush()
        return relation

    async def get_group_access_relation(
        self,
        *,
        group_id: UUID,
        access_id: UUID,
    ) -> RightGroupAccessModel | None:

        return await self._session.get(
            RightGroupAccessModel,
            {"group_id": group_id, "access_id": access_id},
        )

    async def list_group_accesses(self, group_id: UUID) -> list[AccessModel]:

        result = await self._session.scalars(
            select(AccessModel)
            .join(
                RightGroupAccessModel,
                RightGroupAccessModel.access_id == AccessModel.id,
            )
            .where(RightGroupAccessModel.group_id == group_id)
            .order_by(AccessModel.name)
        )
        return list(result)

    async def list_access_groups(self, access_id: UUID) -> list[RightGroupModel]:

        result = await self._session.scalars(
            select(RightGroupModel)
            .join(
                RightGroupAccessModel,
                RightGroupAccessModel.group_id == RightGroupModel.id,
            )
            .where(RightGroupAccessModel.access_id == access_id)
            .order_by(RightGroupModel.name)
        )
        return list(result)

    async def add_group_conflict(
        self,
        *,
        group_id: UUID,
        conflicting_group_id: UUID,
    ) -> RightGroupConflictModel:

        conflict = RightGroupConflictModel(
            group_id=group_id,
            conflicting_group_id=conflicting_group_id,
        )
        self._session.add(conflict)
        await self._session.flush()
        return conflict

    async def get_group_conflict(
        self,
        *,
        group_id: UUID,
        conflicting_group_id: UUID,
    ) -> RightGroupConflictModel | None:

        return await self._session.get(
            RightGroupConflictModel,
            {"group_id": group_id, "conflicting_group_id": conflicting_group_id},
        )

    async def list_group_conflicts(self, group_id: UUID) -> list[RightGroupModel]:

        conflict_rows = await self._session.execute(
            select(RightGroupConflictModel).where(
                or_(
                    RightGroupConflictModel.group_id == group_id,
                    RightGroupConflictModel.conflicting_group_id == group_id,
                )
            )
        )

        conflict_group_ids = [
            row.conflicting_group_id if row.group_id == group_id else row.group_id
            for row in conflict_rows.scalars()
        ]

        if not conflict_group_ids:
            return []

        result = await self._session.scalars(
            select(RightGroupModel)
            .where(RightGroupModel.id.in_(conflict_group_ids))
            .order_by(RightGroupModel.name)
        )
        return list(result)


    async def create_access_request(
        self,
        *,
        user_id: str,
        operation: str,
        target_type: str,
        target_id: UUID,
        status: str,
    ) -> AccessRequestModel:

        request = AccessRequestModel(
            user_id=user_id,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            status=status,
        )
        self._session.add(request)
        await self._session.flush()
        return request

    async def get_access_request(
        self,
        request_id: UUID,
    ) -> AccessRequestModel | None:

        return await self._session.get(AccessRequestModel, request_id)

    async def list_user_requests(
        self,
        user_id: str,
    ) -> list[AccessRequestModel]:

        result = await self._session.scalars(
            select(AccessRequestModel)
            .where(AccessRequestModel.user_id == user_id)
            .order_by(AccessRequestModel.created_at.desc())
        )
        return list(result)

    async def update_request_decision(
        self,
        request: AccessRequestModel,
        *,
        status: str,
        rejection_reason: str | None,
        modified_by: str,
    ) -> AccessRequestModel:

        now = utc_now()
        request.status = status
        request.rejection_reason = rejection_reason
        request.last_modified_at = now
        request.last_modified_by = modified_by

        await self._session.flush()
        return request

    async def get_active_user_right_group(
        self,
        user_id: str,
    ) -> UserRightGroupModel | None:

        result = await self._session.scalars(
            select(UserRightGroupModel)
            .where(
                UserRightGroupModel.user_id == user_id,
                UserRightGroupModel.is_active.is_(True),
            )
            .limit(1)
        )
        return result.first()

    async def deactivate_user_right_group(
        self,
        assignment: UserRightGroupModel,
        *,
        modified_by: str,
    ) -> UserRightGroupModel:

        now = utc_now()
        assignment.is_active = False
        assignment.last_modified_at = now
        assignment.last_modified_by = modified_by

        await self._session.flush()
        return assignment

    async def create_user_right_group(
        self,
        *,
        user_id: str,
        group_id: UUID,
        modified_by: str,
    ) -> UserRightGroupModel:

        now = utc_now()
        assignment = UserRightGroupModel(
            user_id=user_id,
            group_id=group_id,
            is_active=True,
            last_modified_at=now,
            last_modified_by=modified_by,
        )
        self._session.add(assignment)
        await self._session.flush()
        return assignment

    async def get_active_user_access(
        self,
        *,
        user_id: str,
        access_id: UUID,
    ) -> UserAccessModel | None:

        result = await self._session.scalars(
            select(UserAccessModel)
            .where(
                UserAccessModel.user_id == user_id,
                UserAccessModel.access_id == access_id,
                UserAccessModel.is_active.is_(True),
            )
            .limit(1)
        )
        return result.first()


    async def create_user_access(
        self,
        *,
        user_id: str,
        access_id: UUID,
        modified_by: str,
    ) -> UserAccessModel:

        now = utc_now()
        user_access = UserAccessModel(
            user_id=user_id,
            access_id=access_id,
            is_active=True,
            last_modified_at=now,
            last_modified_by=modified_by,
        )
        self._session.add(user_access)
        await self._session.flush()
        return user_access

    async def deactivate_user_access(
        self,
        user_access: UserAccessModel,
        *,
        modified_by: str,
    ) -> UserAccessModel:

        now = utc_now()
        user_access.is_active = False
        user_access.last_modified_at = now
        user_access.last_modified_by = modified_by

        await self._session.flush()
        return user_access

    async def list_active_user_accesses_with_details(
        self,
        user_id: str,
    ) -> list[UserAccessModel]:

        from sqlalchemy.orm import joinedload

        result = await self._session.scalars(
            select(UserAccessModel)
            .options(joinedload(UserAccessModel.access))
            .where(
                UserAccessModel.user_id == user_id,
                UserAccessModel.is_active.is_(True),
            )
            .order_by(UserAccessModel.created_at)
        )
        return list(result)

    async def get_active_user_right_group_with_details(
        self,
        user_id: str,
    ) -> UserRightGroupModel | None:

        from sqlalchemy.orm import joinedload

        result = await self._session.scalars(
            select(UserRightGroupModel)
            .options(
                joinedload(UserRightGroupModel.group)
                .joinedload(RightGroupModel.accesses)
                .joinedload(RightGroupAccessModel.access)
            )
            .where(
                UserRightGroupModel.user_id == user_id,
                UserRightGroupModel.is_active.is_(True),
            )
            .limit(1)
        )
        return result.first()