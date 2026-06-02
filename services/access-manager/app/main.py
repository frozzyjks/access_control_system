import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from app.api import router as request_router
from app.clients import ResourceCatalogClient
from app.config import get_settings
from app.kafka import KafkaAccessRequestEventPublisher


class HealthResponse(BaseModel):
    status: str
    service: str


def configure_logging(log_level: str) -> None:

    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


settings = get_settings()

configure_logging(settings.log_level)

logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:

    app.state.access_request_event_publisher = KafkaAccessRequestEventPublisher(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        topic=settings.access_request_topic,
        logger=logger,
    )

    app.state.resource_catalog_client = ResourceCatalogClient(
        base_url=settings.resource_catalog_url,
        timeout_seconds=settings.resource_catalog_timeout_seconds,
        logger=logger,
    )

    try:
        yield
    finally:
        await app.state.resource_catalog_client.close()
        await app.state.access_request_event_publisher.close()


app = FastAPI(title="Access Manager", version="0.1.0", lifespan=lifespan)

app.include_router(request_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:

    logger.debug("Healthcheck requested")
    return HealthResponse(status="ok", service=settings.service_name)
