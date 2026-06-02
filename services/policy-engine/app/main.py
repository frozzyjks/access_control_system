import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from app.clients import ResourceCatalogClient
from app.config import get_settings
from app.consumer import AccessRequestConsumer


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

    logger.info("Starting Policy Engine")

    resource_catalog_client = ResourceCatalogClient(
        base_url=settings.resource_catalog_url,
        timeout_seconds=settings.resource_catalog_timeout_seconds,
        logger=logger,
    )

    consumer = AccessRequestConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        topic=settings.kafka_access_request_topic,
        group_id=settings.kafka_consumer_group_id,
        resource_catalog_client=resource_catalog_client,
        logger=logger,
    )

    await consumer.start()

    app.state.consumer = consumer
    app.state.resource_catalog_client = resource_catalog_client

    logger.info("Policy Engine started successfully")

    try:
        yield
    finally:
        logger.info("Shutting down Policy Engine")
        await consumer.stop()
        await resource_catalog_client.close()
        logger.info("Policy Engine stopped")


app = FastAPI(
    title="Policy Engine",
    version="0.2.0",
    description=(
        "Policy Engine worker. "
        "Reads access.requests from Kafka, validates against Resource Catalog, "
        "sends APPROVED/REJECTED decisions back to Resource Catalog. "
        "No public business endpoints."
    ),
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:

    logger.debug("Healthcheck requested")
    return HealthResponse(status="ok", service=settings.service_name)