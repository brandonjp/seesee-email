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

    # Which client IPs may set X-Forwarded-Proto / X-Forwarded-For. Passed
    # straight to uvicorn's `forwarded_allow_ips`.
    #
    # SeeSee is designed to run behind a reverse proxy that terminates TLS
    # (aiosmtpd speaks no TLS, so the proxy is not optional), and uvicorn's own
    # default of "127.0.0.1" never matches a proxy running in a separate
    # container — Coolify, Docker Compose, and Kubernetes all connect from a
    # private network address. With the default ignored the forwarded scheme is
    # dropped and cookies silently lose their Secure flag, so the default has to
    # cover the containerized case to be useful at all.
    #
    # It covers it by listing the private ranges a containerized proxy actually
    # connects from, rather than "*". "*" would also work, and did until
    # 0.21.0-dev — but it trusts *any* client that can open a TCP connection to
    # this port, so on a directly-exposed instance an attacker could forge
    # X-Forwarded-For and make every entry in the access log say whatever they
    # want, destroying the audit trail exactly when it matters. Private ranges
    # cost nothing on a normal deploy and remove that.
    #
    # Set this explicitly if the proxy reaches SeeSee from a public address
    # (a proxy on a different host, no private network between them) — nothing
    # here will match it and the forwarded scheme will be dropped. Cookies stay
    # Secure in that case only because `cookies_are_secure()` also honours an
    # https:// SEESEE_BASE_URL, which the startup warning in main.py nags about.
    # "*" is still accepted for anyone who wants the old behaviour back.
    #
    # Requires uvicorn >= 0.31 (older versions compare these as plain strings
    # and would match nothing) — pinned in pyproject.toml.
    forwarded_allow_ips: str = (
        "127.0.0.0/8,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7"
    )

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
