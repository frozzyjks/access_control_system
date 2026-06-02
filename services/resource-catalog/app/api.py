from collections.abc import AsyncGenerator
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas import (
    AccessCreate,
    AccessRead,
    AccessRequestCreate,
    AccessRequestRead,
    AddAccessToGroup,
    AddGroupConflict,
    ApplyDecision,
    ErrorResponse,
    GroupAccessRead,
    GroupConflictRead,
    ResourceCreate,
    ResourceRead,
    RightGroupCreate,
    RightGroupRead,
    UserPermissionsRead,
)
from app.service import (
    CatalogError,
    EntityAlreadyExistsError,
    EntityNotFoundError,
    InvalidCatalogOperationError,
    ResourceCatalogService,
)


router = APIRouter()

internal_router = APIRouter(prefix="/internal")


async def get_catalog_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[ResourceCatalogService, None]:

    yield ResourceCatalogService(session)


def raise_http_error(exc: Exception) -> None:

    if isinstance(exc, EntityNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc

    if isinstance(exc, EntityAlreadyExistsError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc

    if isinstance(exc, InvalidCatalogOperationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc

    raise exc


@router.post(
    "/resources",
    response_model=ResourceRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
    tags=["resources"],
)
async def create_resource(
    payload: ResourceCreate,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> ResourceRead:

    try:
        resource = await service.create_resource(payload)
        return ResourceRead.model_validate(resource)
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.get(
    "/resources/{resource_id}/accesses",
    response_model=list[AccessRead],
    responses={404: {"model": ErrorResponse}},
    tags=["resources"],
)
async def list_resource_accesses(
    resource_id: UUID,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> list[AccessRead]:

    try:
        accesses = await service.list_resource_accesses(resource_id)
        return [AccessRead.model_validate(a) for a in accesses]
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.post(
    "/accesses",
    response_model=AccessRead,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    tags=["accesses"],
)
async def create_access(
    payload: AccessCreate,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> AccessRead:

    try:
        access = await service.create_access(payload)
        return AccessRead.model_validate(access)
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.get(
    "/accesses/{access_id}",
    response_model=AccessRead,
    responses={404: {"model": ErrorResponse}},
    tags=["accesses"],
)
async def get_access(
    access_id: UUID,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> AccessRead:

    try:
        access = await service.get_access(access_id)
        return AccessRead.model_validate(access)
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.post(
    "/right-groups",
    response_model=RightGroupRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
    tags=["right-groups"],
)
async def create_right_group(
    payload: RightGroupCreate,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> RightGroupRead:

    try:
        group = await service.create_right_group(payload)
        return RightGroupRead.model_validate(group)
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.get(
    "/right-groups/{group_id}",
    response_model=RightGroupRead,
    responses={404: {"model": ErrorResponse}},
    tags=["right-groups"],
)
async def get_right_group(
    group_id: UUID,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> RightGroupRead:

    try:
        group = await service.get_right_group(group_id)
        return RightGroupRead.model_validate(group)
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.post(
    "/right-groups/{group_id}/accesses",
    response_model=GroupAccessRead,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}},
    tags=["right-groups"],
)
async def add_access_to_group(
    group_id: UUID,
    payload: AddAccessToGroup,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> GroupAccessRead:

    try:
        relation = await service.add_access_to_group(
            group_id=group_id,
            access_id=payload.access_id,
        )
        return GroupAccessRead.model_validate(relation)
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.get(
    "/right-groups/{group_id}/accesses",
    response_model=list[AccessRead],
    responses={404: {"model": ErrorResponse}},
    tags=["right-groups"],
)
async def list_group_accesses(
    group_id: UUID,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> list[AccessRead]:

    try:
        accesses = await service.list_group_accesses(group_id)
        return [AccessRead.model_validate(a) for a in accesses]
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.post(
    "/right-groups/{group_id}/conflicts",
    response_model=GroupConflictRead,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["right-groups"],
)
async def add_group_conflict(
    group_id: UUID,
    payload: AddGroupConflict,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> GroupConflictRead:

    try:
        conflict = await service.add_group_conflict(
            group_id=group_id,
            conflicting_group_id=payload.conflicting_group_id,
        )
        return GroupConflictRead.model_validate(conflict)
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.get(
    "/right-groups/{group_id}/conflicts",
    response_model=list[RightGroupRead],
    responses={404: {"model": ErrorResponse}},
    tags=["right-groups"],
)
async def list_group_conflicts(
    group_id: UUID,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> list[RightGroupRead]:

    try:
        groups = await service.list_group_conflicts(group_id)
        return [RightGroupRead.model_validate(g) for g in groups]
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.get(
    "/requests/{request_id}",
    response_model=AccessRequestRead,
    responses={404: {"model": ErrorResponse}},
    tags=["requests"],
)
async def get_access_request(
    request_id: UUID,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> AccessRequestRead:

    try:
        request = await service.get_access_request(request_id)
        return AccessRequestRead.model_validate(request)
    except CatalogError as exc:
        raise_http_error(exc)
        raise


@router.get(
    "/requests",
    response_model=list[AccessRequestRead],
    tags=["requests"],
)
async def list_user_requests(
    user_id: str,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> list[AccessRequestRead]:

    requests = await service.list_user_requests(user_id)
    return [AccessRequestRead.model_validate(r) for r in requests]


@router.get(
    "/users/{user_id}/permissions",
    response_model=UserPermissionsRead,
    tags=["permissions"],
)
async def get_user_permissions(
    user_id: str,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> UserPermissionsRead:

    return await service.get_user_permissions(user_id)


@internal_router.post(
    "/requests",
    response_model=AccessRequestRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
    tags=["internal"],
)
async def create_access_request(
    payload: AccessRequestCreate,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> AccessRequestRead:

    request = await service.create_access_request(payload)
    return AccessRequestRead.model_validate(request)


@internal_router.post(
    "/requests/{request_id}/decision",
    response_model=AccessRequestRead,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["internal"],
)
async def apply_decision(
    request_id: UUID,
    payload: ApplyDecision,
    service: ResourceCatalogService = Depends(get_catalog_service),
) -> AccessRequestRead:

    try:
        request = await service.apply_decision(request_id, payload)
        return AccessRequestRead.model_validate(request)
    except CatalogError as exc:
        raise_http_error(exc)
        raise