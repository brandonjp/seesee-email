"""Tests for the web UI — session auth, page rendering, and redirects."""

from httpx import AsyncClient

from seesee.auth import SESSION_COOKIE_NAME, create_session_token
from seesee.config import settings


def _get_session_cookie(username: str = "admin") -> str:
    """Create a valid session token for testing."""
    secret_key = settings.secret_key or settings.admin_password
    return create_session_token(username, secret_key)


# ---------------------------------------------------------------------------
# Login / Logout / Session
# ---------------------------------------------------------------------------


async def test_login_page_renders(client: AsyncClient) -> None:
    """GET /login returns the login form."""
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert "Sign in" in resp.text
    assert "username" in resp.text
    assert "password" in resp.text


async def test_login_success_sets_cookie(client: AsyncClient) -> None:
    """POST /login with valid credentials sets session cookie and redirects."""
    resp = await client.post(
        "/login",
        data={"username": "admin", "password": "testpassword"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert SESSION_COOKIE_NAME in resp.cookies


async def test_login_invalid_password(client: AsyncClient) -> None:
    """POST /login with wrong password returns 401 with error."""
    resp = await client.post(
        "/login",
        data={"username": "admin", "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.text


async def test_login_invalid_username(client: AsyncClient) -> None:
    """POST /login with wrong username returns 401 with error."""
    resp = await client.post(
        "/login",
        data={"username": "notadmin", "password": "testpassword"},
    )
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.text


async def test_logout_clears_cookie(client: AsyncClient) -> None:
    """POST /logout clears the session cookie and redirects to login."""
    resp = await client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    # Cookie should be cleared (max-age=0 or deleted)
    cookie_header = resp.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in cookie_header


async def test_unauthenticated_redirect_to_login(client: AsyncClient) -> None:
    """Accessing protected pages without session redirects to /login."""
    for path in ["/", "/emails", "/apps"]:
        resp = await client.get(path, follow_redirects=False)
        assert resp.status_code == 303, f"Expected 303 for {path}, got {resp.status_code}"
        assert resp.headers["location"] == "/login"


async def test_expired_session_redirects_to_login(client: AsyncClient) -> None:
    """An expired session token should redirect to /login."""
    # Create a token with a different secret so it won't validate
    token = create_session_token("admin", "wrong-secret-key")
    resp = await client.get(
        "/",
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


async def test_invalid_session_token_redirects(client: AsyncClient) -> None:
    """A garbage session token redirects to /login."""
    resp = await client.get(
        "/",
        cookies={SESSION_COOKIE_NAME: "garbage-token"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


async def test_dashboard_renders_empty(client: AsyncClient) -> None:
    """Dashboard shows empty/onboarding state when no apps exist."""
    token = _get_session_cookie()
    resp = await client.get("/", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "Dashboard" in resp.text
    assert "No apps registered yet" in resp.text


async def test_dashboard_renders_with_data(client: AsyncClient, admin_auth_header: dict) -> None:
    """Dashboard shows stats when apps and emails exist."""
    # Create an app
    app_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Dashboard Test"},
        headers=admin_auth_header,
    )
    assert app_resp.status_code == 201
    app_data = app_resp.json()

    # Log an email
    await client.post(
        "/api/v1/log",
        json={
            "to": ["user@example.com"],
            "from": "sender@example.com",
            "subject": "Dashboard test email",
        },
        headers={"Authorization": f"Bearer {app_data['api_key']}"},
    )

    token = _get_session_cookie()
    resp = await client.get("/", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "Dashboard" in resp.text
    assert "Total Emails" in resp.text
    assert "Dashboard Test" in resp.text


# ---------------------------------------------------------------------------
# Email list
# ---------------------------------------------------------------------------


async def test_emails_page_empty(client: AsyncClient) -> None:
    """Email list shows empty state when no emails exist."""
    token = _get_session_cookie()
    resp = await client.get("/emails", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "Emails" in resp.text
    assert "No emails yet" in resp.text


async def test_emails_page_with_data(client: AsyncClient, admin_auth_header: dict) -> None:
    """Email list shows emails when they exist."""
    # Create app + email
    app_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Email List Test"},
        headers=admin_auth_header,
    )
    app_data = app_resp.json()
    await client.post(
        "/api/v1/log",
        json={
            "to": ["recipient@example.com"],
            "from": "sender@example.com",
            "subject": "Test Subject Line",
            "status": "sent",
        },
        headers={"Authorization": f"Bearer {app_data['api_key']}"},
    )

    token = _get_session_cookie()
    resp = await client.get("/emails", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "Test Subject Line" in resp.text
    assert "sender@example.com" in resp.text


async def test_emails_page_search(client: AsyncClient, admin_auth_header: dict) -> None:
    """Email list supports search via q param."""
    app_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Search Test"},
        headers=admin_auth_header,
    )
    app_data = app_resp.json()
    await client.post(
        "/api/v1/log",
        json={
            "to": ["user@example.com"],
            "from": "sender@example.com",
            "subject": "Unique Searchable Subject",
        },
        headers={"Authorization": f"Bearer {app_data['api_key']}"},
    )

    token = _get_session_cookie()
    # Search should find it
    resp = await client.get("/emails?q=Searchable", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "Unique Searchable Subject" in resp.text


async def test_emails_page_no_results_filter(client: AsyncClient) -> None:
    """Email list shows 'no match' state when filters produce no results."""
    token = _get_session_cookie()
    resp = await client.get("/emails?status=nonexistent", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "No emails match" in resp.text


# ---------------------------------------------------------------------------
# Email detail
# ---------------------------------------------------------------------------


async def test_email_detail_renders(client: AsyncClient, admin_auth_header: dict) -> None:
    """Email detail page shows the email data."""
    app_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Detail Test"},
        headers=admin_auth_header,
    )
    app_data = app_resp.json()
    log_resp = await client.post(
        "/api/v1/log",
        json={
            "to": ["to@example.com"],
            "from": "from@example.com",
            "subject": "Detail Page Subject",
            "body_html": "<p>Hello</p>",
            "body_text": "Hello",
            "provider": "resend",
        },
        headers={"Authorization": f"Bearer {app_data['api_key']}"},
    )
    email_id = log_resp.json()["id"]

    token = _get_session_cookie()
    resp = await client.get(f"/emails/{email_id}", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "Detail Page Subject" in resp.text
    assert "from@example.com" in resp.text
    assert "to@example.com" in resp.text
    assert "Preview" in resp.text
    assert "HTML Source" in resp.text
    assert "Metadata" in resp.text
    assert "resend" in resp.text


async def test_email_detail_not_found(client: AsyncClient) -> None:
    """Email detail returns 404 for non-existent ID."""
    token = _get_session_cookie()
    resp = await client.get("/emails/nonexistent-id", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 404
    assert "Email not found" in resp.text


# ---------------------------------------------------------------------------
# Apps page
# ---------------------------------------------------------------------------


async def test_apps_page_empty(client: AsyncClient) -> None:
    """Apps page shows empty state when no apps exist."""
    token = _get_session_cookie()
    resp = await client.get("/apps", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "Apps" in resp.text
    assert "No apps yet" in resp.text


async def test_apps_page_with_data(client: AsyncClient, admin_auth_header: dict) -> None:
    """Apps page lists registered apps."""
    await client.post(
        "/api/v1/apps",
        json={"name": "Listed App"},
        headers=admin_auth_header,
    )

    token = _get_session_cookie()
    resp = await client.get("/apps", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "Listed App" in resp.text


async def test_apps_create_via_form(client: AsyncClient) -> None:
    """POST /apps creates an app and redirects with credentials."""
    token = _get_session_cookie()
    resp = await client.post(
        "/apps",
        data={"name": "Form Created App", "body_storage_mode": "full"},
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/apps?created=")
    assert "api_key" in location
    assert "smtp_username" in location


async def test_apps_rotate_key(client: AsyncClient, admin_auth_header: dict) -> None:
    """POST /apps/{id}/rotate-key rotates key and redirects."""
    app_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Rotate Test"},
        headers=admin_auth_header,
    )
    app_id = app_resp.json()["id"]

    token = _get_session_cookie()
    resp = await client.post(
        f"/apps/{app_id}/rotate-key",
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/apps?rotated_key=ss_")
