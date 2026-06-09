from uuid import UUID
from fastapi import APIRouter, Depends, Request, status
from app.clients import (
    AccessRequestsGateway,
    PermissionsGateway,
    ResourcesGateway,
    RightGroupsGateway,
)
from app.kafka import AccessRequestEventPublisher
from app.schemas import (
    AccessRead,
    AccessRequestCreate,
    AccessRequestRead,
    ErrorResponse,
    UserPermissionsRead,
    ResourceRead,
    RightGroupRead,
)
from app.service import submit_access_request


router = APIRouter()


def get_event_publisher(request: Request) -> AccessRequestEventPublisher:
    return request.app.state.access_request_event_publisher


def get_requests_gateway(request: Request) -> AccessRequestsGateway:
    return request.app.state.catalog_gateways.requests


def get_resources_gateway(request: Request) -> ResourcesGateway:
    return request.app.state.catalog_gateways.resources


def get_right_groups_gateway(request: Request) -> RightGroupsGateway:
    return request.app.state.catalog_gateways.right_groups


def get_permissions_gateway(request: Request) -> PermissionsGateway:
    return request.app.state.catalog_gateways.permissions


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
    requests: AccessRequestsGateway = Depends(get_requests_gateway),
    publisher: AccessRequestEventPublisher = Depends(get_event_publisher),
) -> AccessRequestRead:

    return await submit_access_request(
        payload,
        requests=requests,
        publisher=publisher,
    )


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
    requests: AccessRequestsGateway = Depends(get_requests_gateway),
) -> AccessRequestRead:

    return await requests.get(request_id)


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
    requests: AccessRequestsGateway = Depends(get_requests_gateway),
) -> list[AccessRequestRead]:

    return await requests.list_for_user(user_id)


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
    permissions: PermissionsGateway = Depends(get_permissions_gateway),
) -> UserPermissionsRead:

    return await permissions.get_for_user(user_id)


@router.get(
    "/resources",
    response_model=list[ResourceRead],
    responses={
        502: {"model": ErrorResponse, "description": "Resource Catalog unavailable"},
    },
    tags=["resources"],
)
async def list_resources(
    resources: ResourcesGateway = Depends(get_resources_gateway),
) -> list[ResourceRead]:

    return await resources.list_resources()


@router.get(
    "/right-groups",
    response_model=list[RightGroupRead],
    responses={
        502: {"model": ErrorResponse, "description": "Resource Catalog unavailable"},
    },
    tags=["right-groups"],
)
async def list_right_groups(
    right_groups: RightGroupsGateway = Depends(get_right_groups_gateway),
) -> list[RightGroupRead]:

    return await right_groups.list_right_groups()


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
    resources: ResourcesGateway = Depends(get_resources_gateway),
) -> list[AccessRead]:

    return await resources.list_accesses(resource_id)
