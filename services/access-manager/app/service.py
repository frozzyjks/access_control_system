from app.clients import AccessRequestsGateway
from app.kafka import AccessRequestEventPublisher
from app.schemas import AccessRequestCreate, AccessRequestRead


class RequestPublicationError(Exception):

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def submit_access_request(
    payload: AccessRequestCreate,
    *,
    requests: AccessRequestsGateway,
    publisher: AccessRequestEventPublisher,
) -> AccessRequestRead:

    request = await requests.create(payload)

    try:
        await publisher.publish_request_created(request)
    except Exception as exc:
        raise RequestPublicationError(
            "Access request was saved, but Kafka event publication failed"
            f"Request ID: {request.id}"
        ) from exc

    return request