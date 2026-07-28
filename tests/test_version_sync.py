"""Guard against version drift between pyproject.toml and seesee.__version__.

The app surfaces ``seesee.__version__`` at runtime (FastAPI docs, the ``/health``
endpoint, and the web UI sidebar/footer), while packaging and the docs-site
footer read the version from ``pyproject.toml``. These are two separate literals
and have drifted before (a bump to one but not the other shipped a UI showing a
stale version). This test fails CI the moment they disagree.
"""

import tomllib
from pathlib import Path

import seesee

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_version_matches_pyproject():
    """seesee.__version__ must equal the version declared in pyproject.toml."""
    with _PYPROJECT.open("rb") as f:
        pyproject_version = tomllib.load(f)["project"]["version"]

    assert seesee.__version__ == pyproject_version, (
        f"Version drift: seesee.__version__ is {seesee.__version__!r} but "
        f"pyproject.toml declares {pyproject_version!r}. Bump both together "
        "(pyproject.toml and seesee/__init__.py)."
    )


def test_uvicorn_is_configured_to_trust_the_proxy():
    """`uvicorn.run()` kwargs are not exercised by any request-level test, and a
    silent regression here would quietly un-Secure the session and flash
    cookies on every HTTPS deployment (see test_ui.py's forwarded-proto test).
    """
    import inspect

    from seesee import __main__

    source = inspect.getsource(__main__.main)
    assert "proxy_headers=True" in source
    assert "forwarded_allow_ips=settings.forwarded_allow_ips" in source
