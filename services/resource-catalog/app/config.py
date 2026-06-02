from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "resource-catalog"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://resource_catalog:resource_catalog@resource-catalog-db:5432/resource_catalog"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()