from collections.abc import Awaitable
from typing import TypeVar
from uuid import UUID
from app.clients import ResourceCatalogClient, ResourceCatalogClientError
from app.kafka import AccessRequestEventPublisher
from app.schemas import (
    AccessRead,
    AccessRequestCreate,
    AccessRequestRead,
    UserPermissionsRead,
)


_T = TypeVar("_T")


class AccessManagerError(Exception):

    def __init__(self, message: str) -> None:

        super().__init__(message)
        self.message = message


class RequestNotFoundError(AccessManagerError):
    """Raised when Resource Catalog returns 404 for a request"""


class ResourceCatalogProxyError(AccessManagerError):

    def __init__(self, message: str, status_code: int | None = None) -> None:

        super().__init__(message)
        self.status_code = status_code


class RequestPublicationError(AccessManagerError):
    """Raised when request was saved in Resource Catalog but Kafka publish failed"""


class AccessRequestService:

    def __init__(
        self,
        *,
        resource_catalog_client: ResourceCatalogClient,
        event_publisher: AccessRequestEventPublisher,
    ) -> None:

        self._resource_catalog_client = resource_catalog_client
        self._event_publisher = event_publisher

    async def create_request(
        self,
        payload: AccessRequestCreate,
    ) -> AccessRequestRead:

        request = await self._proxy(
            self._resource_catalog_client.create_access_request(payload),
        )
        await self._publish_request_created(request)
        return request

    async def get_request(self, request_id: UUID) -> AccessRequestRead:

        return await self._proxy(
            self._resource_catalog_client.get_access_request(request_id),
        )

    async def list_user_requests(self, user_id: str) -> list[AccessRequestRead]:

        return await self._proxy(
            self._resource_catalog_client.list_user_requests(user_id),
        )

    async def get_user_permissions(self, user_id: str) -> UserPermissionsRead:

        return await self._proxy(
            self._resource_catalog_client.get_user_permissions(user_id),
        )

    async def list_resource_accesses(
        self,
        resource_id: UUID,
    ) -> list[AccessRead]:

        return await self._proxy(
            self._resource_catalog_client.list_resource_accesses(resource_id),
        )

    async def _publish_request_created(
        self,
        request: AccessRequestRead,
    ) -> None:

        try:
            await self._event_publisher.publish_request_created(request)
        except Exception as exc:

            raise RequestPublicationError(
                "Access request was saved, but Kafka event publication failed. "
                f"Request ID: {request.id}"
            ) from exc

    # Альтернатива — try/except в каждом методе или декоратор
    @staticmethod
    async def _proxy(coro: Awaitable[_T]) -> _T:

        try:
            return await coro
        except ResourceCatalogClientError as exc:
            if exc.status_code == 404:
                raise RequestNotFoundError(exc.message) from exc

            raise ResourceCatalogProxyError(
                exc.message,
                status_code=exc.status_code,
            ) from exc