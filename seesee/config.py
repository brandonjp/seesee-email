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

    # MCP server (mounted at /mcp; Bearer ss_mgmt_ keys only)
    mcp_enabled: bool = True

    # Retention
    retention_max_count: int = 1000
    retention_max_age_days: int = 90
    retention_max_storage_mb: int = 500
    retention_cleanup_interval_minutes: int = 60

    # Body degradation (0 = disabled, never degrade)
    retention_degrade_to_text_days: int = 0
    retention_degrade_to_preview_days: int = 0

    # Session
    secret_key: str = ""
    session_max_age_days: int = 7

    # UI
    theme: str = "system"

    # Build metadata — baked into the image at build time (see Dockerfile /
    # build.yml). UTC ISO 8601 timestamp, e.g. "2026-07-01T23:18:00". Empty
    # when running from source; the UI shows "local dev" in that case.
    build_time: str = ""

    # Display timezone — controls how dates are shown in admin views.
    # IANA timezone string (e.g. "America/Chicago", "Europe/London").
    # Does NOT affect storage (always UTC) or API responses (always UTC ISO 8601).
    display_timezone: str = "UTC"

    # Webhook secrets (per-provider, optional — skip verification if empty)
    webhook_secret_resend: str = ""
    webhook_secret_sendgrid: str = ""

    # Logging
    log_level: str = "info"


settings = SeeSeeSettings()
