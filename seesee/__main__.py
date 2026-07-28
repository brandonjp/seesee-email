"""Entry point for `python -m seesee`."""

import uvicorn

from seesee.config import settings


def main() -> None:
    """Start the SeeSee application server."""
    uvicorn.run(
        "seesee.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
        # Trust the reverse proxy's X-Forwarded-Proto so request.url.scheme
        # reports "https" behind TLS termination. Without this, uvicorn's
        # default forwarded_allow_ips="127.0.0.1" never matches a proxy in a
        # separate container, the header is dropped, and session/flash cookies
        # lose their Secure flag on an HTTPS deployment. The default trusts the
        # private ranges a containerized proxy connects from, not everything —
        # see the setting's comment in seesee/config.py.
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
