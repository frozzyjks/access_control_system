import logging
from uuid import UUID
import httpx
from app.schemas import (
    AccessRead,
    AccessRequestRead,
    ApplyDecisionRequest,
    RightGroupConflictRead,
    RightGroupRead,
    UserPermissionsRead,
)


class ResourceCatalogClientError(Exception):

    def __init__(self, message: str, status_code: int | None = None) -> None:

        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ResourceCatalogClient:

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

    async def close(self) -> None:

        await self._client.aclose()


    async def get_access_request(
        self,
        request_id: UUID,
    ) -> AccessRequestRead:

        data = await self._request_json(
            method="GET",
            url=f"/requests/{request_id}",
        )
        return AccessRequestRead.model_validate(data)


    async def get_access(self, access_id: UUID) -> AccessRead:

        data = await self._request_json(
            method="GET",
            url=f"/accesses/{access_id}",
        )
        return AccessRead.model_validate(data)

    async def get_right_group(self, group_id: UUID) -> RightGroupRead:

        data = await self._request_json(
            method="GET",
            url=f"/right-groups/{group_id}",
        )
        return RightGroupRead.model_validate(data)

    async def list_group_accesses(self, group_id: UUID) -> list[AccessRead]:

        data = await self._request_json(
            method="GET",
            url=f"/right-groups/{group_id}/accesses",
        )
        return [AccessRead.model_validate(item) for item in data]

    async def list_group_conflicts(
        self,
        group_id: UUID,
    ) -> list[RightGroupConflictRead]:

        data = await self._request_json(
            method="GET",
            url=f"/right-groups/{group_id}/conflicts",
        )
        return [
            RightGroupConflictRead(
                group_id=group_id,
                conflicting_group_id=item["id"],
            )
            for item in data
        ]

    async def get_user_permissions(
        self,
        user_id: str,
    ) -> UserPermissionsRead:

        data = await self._request_json(
            method="GET",
            url=f"/users/{user_id}/permissions",
        )

        right_group = None
        if data.get("right_group"):
            right_group = RightGroupRead.model_validate(data["right_group"])

        direct_access_ids = [
            access["id"] for access in data.get("direct_accesses", [])
        ]

        return UserPermissionsRead(
            user_id=data["user_id"],
            right_group=right_group,
            direct_access_ids=direct_access_ids,
        )


    async def apply_decision(
        self,
        request_id: UUID,
        decision: ApplyDecisionRequest,
    ) -> None:

        await self._request_json(
            method="POST",
            url=f"/internal/requests/{request_id}/decision",
            json=decision.model_dump(mode="json"),
        )


    async def _request_json(
        self,
        *,
        method: str,
        url: str,
        json: dict | None = None,
    ) -> dict:

        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json,
            )
        except httpx.TimeoutException as exc:
            self._logger.warning(
                "Resource Catalog request timed out: method=%s url=%s",
                method,
                url,
            )
            raise ResourceCatalogClientError(
                f"Resource Catalog request timed out: {url}",
            ) from exc
        except httpx.RequestError as exc:
            self._logger.warning(
                "Resource Catalog is unavailable: method=%s url=%s error=%s",
                method,
                url,
                exc,
            )
            raise ResourceCatalogClientError(
                f"Resource Catalog is unavailable: {url}",
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
        raise ResourceCatalogClientError(detail, status_code=response.status_code)

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