import logging
from typing import Any
from uuid import UUID
import httpx
from app.schemas import (
    AccessRead,
    AccessRequestCreate,
    AccessRequestRead,
    UserPermissionsRead,
    ResourceRead,
    RightGroupRead,
)


class CatalogUnavailableError(Exception):
    """Directory is unavailable: the network has not responded, or the timeout has expired"""


class CatalogResponseError(Exception):

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class _CatalogHttpClient:

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        logger: logging.Logger,
    ) -> None:

        self._logger = logger
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def request_json(
        self,
        *,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:

        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json,
                params=params,
            )
        except httpx.TimeoutException as exc:
            self._logger.warning(
                "Resource Catalog request timed out: method=%s url=%s",
                method,
                url,
            )
            raise CatalogUnavailableError(
                "Resource Catalog request timed out",
            ) from exc
        except httpx.RequestError as exc:
            self._logger.warning(
                "Resource Catalog is unavailable: method=%s url=%s error=%s",
                method,
                url,
                exc,
            )
            raise CatalogUnavailableError(
                "Resource Catalog is unavailable",
            ) from exc

        if response.is_success:
            return response.json()

        detail = self._extract_error_detail(response)
        self._logger.warning(
            "Resource Catalog returned error: method=%s url=%s status=%s detail=%s",
            method,
            url,
            response.status_code,
            detail,
        )
        raise CatalogResponseError(detail, status_code=response.status_code)

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:

        try:
            payload = response.json()
        except ValueError:
            return response.text or "Resource Catalog request failed"

        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail

        return "Resource Catalog request failed"

    async def close(self) -> None:

        await self._client.aclose()


class AccessRequestsGateway:

    def __init__(self, http: _CatalogHttpClient) -> None:
        self._http = http

    async def create(self, payload: AccessRequestCreate) -> AccessRequestRead:

        data = await self._http.request_json(
            method="POST",
            url="/internal/requests",
            json=payload.model_dump(mode="json"),
        )
        return AccessRequestRead.model_validate(data)

    async def get(self, request_id: UUID) -> AccessRequestRead:
        data = await self._http.request_json(
            method="GET",
            url=f"/requests/{request_id}",
        )
        return AccessRequestRead.model_validate(data)

    async def list_for_user(self, user_id: str) -> list[AccessRequestRead]:
        data = await self._http.request_json(
            method="GET",
            url="/requests",
            params={"user_id": user_id},
        )
        return [AccessRequestRead.model_validate(item) for item in data]


class ResourcesGateway:

    def __init__(self, http: _CatalogHttpClient) -> None:
        self._http = http

    async def list_resources(self) -> list[ResourceRead]:
        data = await self._http.request_json(
            method="GET",
            url="/resources",
        )
        return [ResourceRead.model_validate(item) for item in data]

    async def list_accesses(self, resource_id: UUID) -> list[AccessRead]:
        data = await self._http.request_json(
            method="GET",
            url=f"/resources/{resource_id}/accesses",
        )
        return [AccessRead.model_validate(item) for item in data]


class RightGroupsGateway:

    def __init__(self, http: _CatalogHttpClient) -> None:
        self._http = http

    async def list_right_groups(self) -> list[RightGroupRead]:
        data = await self._http.request_json(
            method="GET",
            url="/right-groups",
        )
        return [RightGroupRead.model_validate(item) for item in data]


class PermissionsGateway:

    def __init__(self, http: _CatalogHttpClient) -> None:
        self._http = http

    async def get_for_user(self, user_id: str) -> UserPermissionsRead:
        data = await self._http.request_json(
            method="GET",
            url=f"/users/{user_id}/permissions",
        )
        return UserPermissionsRead.model_validate(data)


class CatalogGateways:

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        logger: logging.Logger,
    ) -> None:

        self._http = _CatalogHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            logger=logger,
        )
        self.requests = AccessRequestsGateway(self._http)
        self.resources = ResourcesGateway(self._http)
        self.right_groups = RightGroupsGateway(self._http)
        self.permissions = PermissionsGateway(self._http)

    async def close(self) -> None:
        await self._http.close()
