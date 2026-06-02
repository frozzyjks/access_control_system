import logging
from fastapi import FastAPI
from pydantic import BaseModel
from app.api import internal_router, router as catalog_router
from app.config import get_settings


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

app = FastAPI(title="Resource Catalog", version="0.2.0")

app.include_router(catalog_router)

app.include_router(internal_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:

    logger.debug("Healthcheck requested")
    return HealthResponse(status="ok", service=settings.service_name)