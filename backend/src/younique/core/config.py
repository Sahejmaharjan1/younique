from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    cookie_secure: bool = False
    database_url: str = "postgresql+asyncpg://younique_app:younique_app@localhost:5432/younique"
    database_url_migrator: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/younique"
    firebase_project_id: str = "demo-younique"
    firebase_auth_emulator_host: str | None = None
    kek_backend: str = "env"
    master_key: str = ""
    kek_file: str = ""
    kms_key_name: str = ""
    gcs_endpoint: str = "http://localhost:4443"
    gcs_uploads_bucket: str = "younique-uploads-local"
    gcs_artifacts_bucket: str = "younique-artifacts-local"
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    otel_enabled: bool = False
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_capture_content: bool = False
    oidc_emulator: bool = True
    dev_internal_token: str = "dev-internal"
    internal_oidc_audience: str = "https://worker.younique.local"
    web_origin: str = "http://localhost:3000"
    session_idle_days: int = 30
    session_absolute_days: int = 90
    step_up_seconds: int = 300
    rate_limit_per_minute: int = 120
    llm_mode: str = "fake"
    stream_pace_ms: int = 0
    gcs_mode: str = "memory"
    cloud_tasks_url: str = ""
    pubsub_url: str = ""
    scanner_url: str = ""
    scanner_mode: str = "builtin"
    upload_token_secret: str = "dev-upload"
    max_upload_bytes: int = 100_000_000


def get_settings() -> Settings:
    return Settings()
