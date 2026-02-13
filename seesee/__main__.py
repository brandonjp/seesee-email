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
    )


if __name__ == "__main__":
    main()
