"""SeeSee configuration via environment variables.

All settings use the SEESEE_ prefix and are parsed by pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SeeSeeSettings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="SEESEE_", env_file=".env", extra="ignore")

    # Server
    port: int = 8080
    base_url: str = "http://localhost:8080"

    # Auth
    admin_username: str = "admin"
    admin_password: str = ""

    # Database
    db_path: str = "/data/seesee.db"

    # SMTP Ingest
    smtp_enabled: bool = True
    smtp_port: int = 2525
    smtp_relay_host: str = ""
    smtp_relay_port: int = 587
    smtp_relay_username: str = ""
    smtp_relay_password: str = ""
    smtp_relay_tls: bool = True

    # Retention
    retention_max_count: int = 1000
    retention_max_age_days: int = 90
    retention_max_storage_mb: int = 500
    retention_cleanup_interval_minutes: int = 60

    # Session
    secret_key: str = ""
    session_max_age_days: int = 7

    # UI
    theme: str = "system"

    # Logging
    log_level: str = "info"


settings = SeeSeeSettings()
