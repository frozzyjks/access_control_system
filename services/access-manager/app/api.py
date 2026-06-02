from collections.abc import AsyncGenerator
from typing import NoReturn
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.clients import ResourceCatalogClient
from app.kafka import AccessRequestEventPublisher
from app.schemas import (
    AccessRead,
    AccessRequestCreate,
    AccessRequestRead,
    ErrorResponse,
    UserPermissionsRead,
)
from app.service import (
    AccessManagerError,
    AccessRequestService,
    RequestNotFoundError,
    RequestPublicationError,
    ResourceCatalogProxyError,
)


router = APIRouter()


def get_event_publisher(request: Request) -> AccessRequestEventPublisher:
    return request.app.state.access_request_event_publisher


def get_resource_catalog_client(request: Request) -> ResourceCatalogClient:
    return request.app.state.resource_catalog_client


async def get_access_request_service(
    event_publisher: AccessRequestEventPublisher = Depends(get_event_publisher),
    resource_catalog_client: ResourceCatalogClient = Depends(get_resource_catalog_client),
) -> AsyncGenerator[AccessRequestService, None]:

    yield AccessRequestService(
        resource_catalog_client=resource_catalog_client,
        event_publisher=event_publisher,
    )


def raise_http_error(exc: AccessManagerError) -> NoReturn:
    if isinstance(exc, RequestNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc

    if isinstance(exc, RequestPublicationError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc

    if isinstance(exc, ResourceCatalogProxyError):
        upstream_status = exc.status_code
        if upstream_status is None or upstream_status >= 500:
            http_status = status.HTTP_502_BAD_GATEWAY
        else:
            http_status = upstream_status

        raise HTTPException(status_code=http_status, detail=exc.message) from exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=exc.message,
    ) from exc


@router.post(
    "/requests",
    response_model=AccessRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        502: {"model": ErrorResponse, "description": "Resource Catalog unavailable"},
        503: {"model": ErrorResponse, "description": "Kafka publication failed"},
    },
    tags=["requests"],
    summary="Submit access request",
)
async def create_request(
    payload: AccessRequestCreate,
    service: AccessRequestService = Depends(get_access_request_service),
) -> AccessRequestRead:

    try:
        return await service.create_request(payload)
    except AccessManagerError as exc:
        raise_http_error(exc)


@router.get(
    "/requests/{request_id}",
    response_model=AccessRequestRead,
    responses={
        404: {"model": ErrorResponse, "description": "Request not found"},
        502: {"model": ErrorResponse, "description": "Resource Catalog unavailable"},
    },
    tags=["requests"],
    summary="Get request status",
)
async def get_request(
    request_id: UUID,
    service: AccessRequestService = Depends(get_access_request_service),
) -> AccessRequestRead:

    try:
        return await service.get_request(request_id)
    except AccessManagerError as exc:
        raise_http_error(exc)


@router.get(
    "/users/{user_id}/requests",
    response_model=list[AccessRequestRead],
    responses={
        502: {"model": ErrorResponse, "description": "Resource Catalog unavailable"},
    },
    tags=["requests"],
    summary="List user requests",
)
async def list_user_requests(
    user_id: str,
    service: AccessRequestService = Depends(get_access_request_service),
) -> list[AccessRequestRead]:

    try:
        return await service.list_user_requests(user_id)
    except AccessManagerError as exc:
        raise_http_error(exc)


@router.get(
    "/users/{user_id}/permissions",
    response_model=UserPermissionsRead,
    responses={
        502: {"model": ErrorResponse, "description": "Resource Catalog unavailable"},
    },
    tags=["permissions"],
    summary="Get user permissions",
)
async def get_user_permissions(
    user_id: str,
    service: AccessRequestService = Depends(get_access_request_service),
) -> UserPermissionsRead:

    try:
        return await service.get_user_permissions(user_id)
    except AccessManagerError as exc:
        raise_http_error(exc)


@router.get(
    "/resources/{resource_id}/accesses",
    response_model=list[AccessRead],
    responses={
        404: {"model": ErrorResponse, "description": "Resource not found"},
        502: {"model": ErrorResponse, "description": "Resource Catalog unavailable"},
    },
    tags=["resources"],
    summary="List resource accesses",
)
async def list_resource_accesses(
    resource_id: UUID,
    service: AccessRequestService = Depends(get_access_request_service),
) -> list[AccessRead]:

    try:
        return await service.list_resource_accesses(resource_id)
    except AccessManagerError as exc:
        raise_http_error(exc)