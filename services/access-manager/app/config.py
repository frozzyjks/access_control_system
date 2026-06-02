from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "access-manager"
    log_level: str = "INFO"
    kafka_bootstrap_servers: str = "kafka:9092"
    access_request_topic: str = "access.requests"
    resource_catalog_url: str = "http://resource-catalog:8000"
    resource_catalog_timeout_seconds: float = 5.0
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:

    return Settings()