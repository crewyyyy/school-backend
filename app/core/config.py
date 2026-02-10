from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "School Events API"
    app_env: str = "dev"
    api_v1_prefix: str = ""

    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 8 * 60

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/school"

    storage_backend: str = "local"  # local | s3
    media_dir: str = "./media"
    media_base_url: str = "http://localhost:8000/media"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "school-media"
    s3_region: str = "us-east-1"
    s3_public_base_url: str | None = None

    fcm_service_account_json: str = "./secrets/fcm-service-account.json"
    fcm_topic: str = "school_all"

    bootstrap_admin_login: str = "admin"
    bootstrap_admin_password: str = "admin123"
    auto_create_admin: bool = True

    @property
    def media_path(self) -> Path:
        return Path(self.media_dir).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()

