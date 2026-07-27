"""Tests for the web UI — session auth, page rendering, and redirects."""

from httpx import AsyncClient
from itsdangerous import URLSafeTimedSerializer

from seesee import keys
from seesee.auth import SESSION_COOKIE_NAME, create_session_token
from seesee.config import settings
from seesee.csrf import CSRF_FIELD_NAME, make_csrf_token
from seesee.routes.ui import FLASH_COOKIE_NAME, _build_env_vars


def csrf_form(data: dict | None = None) -> dict:
    """Merge a valid CSRF token into form data for session-authenticated POSTs."""
    token = make_csrf_token("admin", "testpassword")
    return {**(data or {}), CSRF_FIELD_NAME: token}


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


async def test_login_username_case_insensitive(client: AsyncClient) -> None:
    """POST /login accepts username regardless of case."""
    for variant in ["Admin", "ADMIN", "aDmIn"]:
        resp = await client.post(
            "/login",
            data={"username": variant, "password": "testpassword"},
            follow_redirects=False,
        )
        assert resp.status_code == 303, (
            f"Expected 303 for username '{variant}', got {resp.status_code}"
        )
        assert SESSION_COOKIE_NAME in resp.cookies


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


def _read_flash(resp) -> dict | None:
    """Decode the flash cookie from a response."""
    cookie = resp.cookies.get(FLASH_COOKIE_NAME)
    if not cookie:
        return None
    secret_key = settings.secret_key or settings.admin_password
    serializer = URLSafeTimedSerializer(secret_key, salt="seesee-flash")
    return serializer.loads(cookie, max_age=60)


async def test_apps_create_via_form(client: AsyncClient) -> None:
    """POST /apps creates an app and redirects with credentials in flash cookie."""
    token = _get_session_cookie()
    resp = await client.post(
        "/apps",
        data=csrf_form({"name": "Form Created App", "body_storage_mode": "full"}),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/apps"
    # Credentials must be in the flash cookie, not the URL
    flash = _read_flash(resp)
    assert flash is not None
    creds = flash["created_credentials"]
    assert creds["api_key"].startswith("ss_")
    assert creds["smtp_username"]


async def test_apps_rotate_key(client: AsyncClient, admin_auth_header: dict) -> None:
    """POST /apps/{id}/rotate-key rotates key and redirects with key in flash cookie."""
    app_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Rotate Test"},
        headers=admin_auth_header,
    )
    app_id = app_resp.json()["id"]

    token = _get_session_cookie()
    resp = await client.post(
        f"/apps/{app_id}/rotate-key",
        data=csrf_form(),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/apps"
    # Key must be in the flash cookie, not the URL
    flash = _read_flash(resp)
    assert flash is not None
    assert flash["rotated_key"].startswith("ss_")


async def test_apps_update_settings(client: AsyncClient, admin_auth_header: dict) -> None:
    """POST /apps/{id}/settings updates storage mode and retention values."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Settings App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    resp = await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "preview",
                "retention_max_count": "250",
                "retention_max_age_days": "30",
                "retention_degrade_to_text_days": "",
                "retention_degrade_to_preview_days": "",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/apps/{app_id}"

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["body_storage_mode"] == "preview"
    assert updated["retention_max_count"] == 250
    assert updated["retention_max_age_days"] == 30


async def test_apps_update_settings_clears_retention(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """Submitting empty retention fields clears the overrides to null."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Clear App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    # First set overrides
    await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "full",
                "retention_max_count": "500",
                "retention_max_age_days": "45",
                "retention_degrade_to_text_days": "",
                "retention_degrade_to_preview_days": "",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    # Then clear them
    resp = await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "full",
                "retention_max_count": "",
                "retention_max_age_days": "",
                "retention_degrade_to_text_days": "",
                "retention_degrade_to_preview_days": "",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["retention_max_count"] is None
    assert updated["retention_max_age_days"] is None


async def test_apps_update_settings_rejects_invalid_mode(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """An invalid body_storage_mode is rejected — no DB change."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Bad Mode App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    resp = await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "bogus",
                "retention_max_count": "",
                "retention_max_age_days": "",
                "retention_degrade_to_text_days": "",
                "retention_degrade_to_preview_days": "",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["body_storage_mode"] == "full"  # unchanged from creation default


async def test_apps_update_settings_rejects_negative_retention(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """A negative retention value is rejected — prior value is left intact."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Neg App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    # Set a known value first
    await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "full",
                "retention_max_count": "100",
                "retention_max_age_days": "",
                "retention_degrade_to_text_days": "",
                "retention_degrade_to_preview_days": "",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    # Negative value must be rejected
    resp = await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "full",
                "retention_max_count": "-5",
                "retention_max_age_days": "",
                "retention_degrade_to_text_days": "",
                "retention_degrade_to_preview_days": "",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["retention_max_count"] == 100  # unchanged


async def test_apps_update_settings_zero_means_system_default(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """A retention value of 0 is stored as NULL — the engine treats them identically."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Zero App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    # Set real overrides first so the coercion has something to clear
    await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "full",
                "retention_max_count": "100",
                "retention_max_age_days": "30",
                "retention_degrade_to_text_days": "7",
                "retention_degrade_to_preview_days": "14",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    resp = await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "full",
                "retention_max_count": "0",
                "retention_max_age_days": "0",
                "retention_degrade_to_text_days": "0",
                "retention_degrade_to_preview_days": "0",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    listed = await client.get("/api/v1/apps", headers=admin_auth_header)
    updated = next(a for a in listed.json() if a["id"] == app_id)
    assert updated["retention_max_count"] is None
    assert updated["retention_max_age_days"] is None
    assert updated["retention_degrade_to_text_days"] is None
    assert updated["retention_degrade_to_preview_days"] is None

    # Read view shows "System default", not a literal 0
    detail = await client.get(f"/apps/{app_id}", cookies={SESSION_COOKIE_NAME: token})
    assert "System default" in detail.text


async def test_app_detail_settings_card(client: AsyncClient, admin_auth_header: dict) -> None:
    """Detail page renders the Settings card; set retention values round-trip."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Card App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    token = _get_session_cookie()

    await client.post(
        f"/apps/{app_id}/settings",
        data=csrf_form(
            {
                "body_storage_mode": "preview",
                "retention_max_count": "111",
                "retention_max_age_days": "22",
                "retention_degrade_to_text_days": "7",
                "retention_degrade_to_preview_days": "14",
            }
        ),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )

    resp = await client.get(f"/apps/{app_id}", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert f'action="/apps/{app_id}/settings"' in resp.text
    assert 'name="body_storage_mode"' in resp.text
    assert 'name="retention_max_count"' in resp.text
    assert 'name="retention_degrade_to_preview_days"' in resp.text
    # The degrade-field values prove the detail SELECT fetches all four columns.
    assert 'value="7"' in resp.text
    assert 'value="14"' in resp.text


# ---------------------------------------------------------------------------
# Integration ENV vars
# ---------------------------------------------------------------------------


def test_build_env_vars_includes_all_sections() -> None:
    """_build_env_vars produces the full var block with section comments."""
    env = _build_env_vars(
        app_id="abc-123",
        slug="my-app",
        api_key="ss_realkey",
        base_url="https://seesee.example.com",
        smtp_port=2525,
    )
    assert "# SeeSee API" in env
    assert "# SMTP connection" in env
    assert "# App identity" in env
    assert "MAIL_SEESEE_API_KEY=ss_realkey" in env
    assert "MAIL_SEESEE_SMTP_HOST=seesee.example.com" in env
    assert "MAIL_SEESEE_SMTP_PORT=2525" in env
    assert "MAIL_SEESEE_SMTP_USERNAME=my-app" in env
    assert "MAIL_SEESEE_SMTP_PASSWORD=ss_realkey" in env
    assert "MAIL_SEESEE_SMTP_ENCRYPTION=null" in env
    assert "MAIL_SEESEE_URL=https://seesee.example.com" in env
    assert "MAIL_SEESEE_APP_ID=abc-123" in env
    assert "MAIL_SEESEE_APP_URL=https://seesee.example.com/apps/abc-123" in env
    assert "MAIL_SEESEE_LOG_URL=https://seesee.example.com/emails?app_id=abc-123" in env


async def test_apps_create_flash_includes_env_vars(client: AsyncClient) -> None:
    """The post-creation flash carries a complete ENV block with the real key."""
    token = _get_session_cookie()
    resp = await client.post(
        "/apps",
        data=csrf_form({"name": "Env Block App", "body_storage_mode": "full"}),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    flash = _read_flash(resp)
    assert flash is not None
    creds = flash["created_credentials"]
    env = creds["env_vars"]
    # Location 1 uses the real key for both API key and SMTP password
    assert f"MAIL_SEESEE_API_KEY={creds['api_key']}" in env
    assert f"MAIL_SEESEE_SMTP_PASSWORD={creds['api_key']}" in env
    assert "MAIL_SEESEE_APP_ID=" in env
    assert "MAIL_SEESEE_APP_URL=" in env
    assert "MAIL_SEESEE_LOG_URL=" in env
    assert "MAIL_SEESEE_SMTP_ENCRYPTION=null" in env


async def test_app_detail_smtp_tab_env_vars(client: AsyncClient, admin_auth_header: dict) -> None:
    """App detail SMTP tab offers the full ENV block with the API key placeholder."""
    app_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Detail Env App"},
        headers=admin_auth_header,
    )
    app_id = app_resp.json()["id"]

    token = _get_session_cookie()
    resp = await client.get(f"/apps/{app_id}", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    # env_vars is rendered via the |tojson filter — credentials not re-shown,
    # so both key and password use the placeholder.
    assert "MAIL_SEESEE_API_KEY=ss_YOUR_API_KEY" in resp.text
    assert "MAIL_SEESEE_SMTP_PASSWORD=ss_YOUR_API_KEY" in resp.text
    assert f"MAIL_SEESEE_APP_ID={app_id}" in resp.text
    assert "MAIL_SEESEE_APP_URL=" in resp.text
    assert "MAIL_SEESEE_LOG_URL=" in resp.text
    assert "MAIL_SEESEE_SMTP_ENCRYPTION=null" in resp.text


# ---------------------------------------------------------------------------
# Settings — management keys
# ---------------------------------------------------------------------------


async def test_settings_shows_keys_section(client: AsyncClient) -> None:
    """Settings page renders the API Keys card."""
    token = _get_session_cookie()
    resp = await client.get("/settings", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert "API Keys" in resp.text


async def test_create_mgmt_key_ui_flow(client: AsyncClient) -> None:
    """POST /settings/keys mints a management key; the plaintext is flashed once."""
    token = _get_session_cookie()
    resp = await client.post(
        "/settings/keys",
        data=csrf_form({"label": "agent", "scopes": ["emails:read", "apps:read"], "expires": "90"}),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings"

    resp2 = await client.get(
        "/settings",
        cookies={SESSION_COOKIE_NAME: token, FLASH_COOKIE_NAME: resp.cookies[FLASH_COOKIE_NAME]},
    )
    assert resp2.status_code == 200
    assert "ss_mgmt_" in resp2.text
    assert "agent" in resp2.text


async def test_create_mgmt_key_invalid_scope_shows_error(client: AsyncClient) -> None:
    """An invalid scope for a management key flashes an error and creates nothing."""
    token = _get_session_cookie()
    resp = await client.post(
        "/settings/keys",
        data=csrf_form({"label": "bad-agent", "scopes": ["emails:write"], "expires": "90"}),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    resp2 = await client.get(
        "/settings",
        cookies={SESSION_COOKIE_NAME: token, FLASH_COOKIE_NAME: resp.cookies[FLASH_COOKIE_NAME]},
    )
    assert resp2.status_code == 200
    assert "Invalid scope" in resp2.text
    assert "bad-agent" not in resp2.text


async def test_revoke_mgmt_key_ui(client: AsyncClient) -> None:
    """Revoking a management key via Settings marks it revoked in the table."""
    token = _get_session_cookie()
    await client.post(
        "/settings/keys",
        data=csrf_form({"label": "revoke-me", "scopes": ["emails:read"], "expires": "90"}),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    key_id = [k["id"] for k in await keys.list_keys(None) if k["label"] == "revoke-me"][0]

    resp = await client.post(
        f"/settings/keys/{key_id}/revoke",
        data=csrf_form(),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings"

    resp2 = await client.get("/settings", cookies={SESSION_COOKIE_NAME: token})
    assert resp2.status_code == 200
    assert "revoked" in resp2.text


async def test_revoke_app_key_via_settings_404(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """An app key's id cannot be revoked via the management-keys settings route."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Settings Revoke App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    app_key_id = (await keys.list_keys(app_id))[0]["id"]

    token = _get_session_cookie()
    resp = await client.post(
        f"/settings/keys/{app_key_id}/revoke",
        data=csrf_form(),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# App detail — per-app keys
# ---------------------------------------------------------------------------


async def test_app_detail_shows_keys_table(client: AsyncClient, admin_auth_header: dict) -> None:
    """App detail page lists the app's default key by prefix."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Keys Table App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]
    key_prefix = (await keys.list_keys(app_id))[0]["key_prefix"]

    token = _get_session_cookie()
    resp = await client.get(f"/apps/{app_id}", cookies={SESSION_COOKIE_NAME: token})
    assert resp.status_code == 200
    assert key_prefix in resp.text


async def test_mint_app_key_ui_flow(client: AsyncClient, admin_auth_header: dict) -> None:
    """POST /apps/{id}/keys mints an app key; the plaintext is flashed once."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Mint Key App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]

    token = _get_session_cookie()
    resp = await client.post(
        f"/apps/{app_id}/keys",
        data=csrf_form({"label": "second-key", "scopes": ["emails:read", "emails:write"]}),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/apps/{app_id}"

    resp2 = await client.get(
        f"/apps/{app_id}",
        cookies={SESSION_COOKIE_NAME: token, FLASH_COOKIE_NAME: resp.cookies[FLASH_COOKIE_NAME]},
    )
    assert resp2.status_code == 200
    assert "ss_" in resp2.text
    assert "second-key" in resp2.text

    app_keys = await keys.list_keys(app_id)
    assert len(app_keys) == 2


async def test_revoke_app_key_ui(client: AsyncClient, admin_auth_header: dict) -> None:
    """Revoking a minted app key via the app detail page marks it revoked."""
    app_resp = await client.post(
        "/api/v1/apps", json={"name": "Revoke Key App"}, headers=admin_auth_header
    )
    app_id = app_resp.json()["id"]

    token = _get_session_cookie()
    await client.post(
        f"/apps/{app_id}/keys",
        data=csrf_form({"label": "revoke-me", "scopes": ["emails:read"]}),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    key_id = [k["id"] for k in await keys.list_keys(app_id) if k["label"] == "revoke-me"][0]

    resp = await client.post(
        f"/apps/{app_id}/keys/{key_id}/revoke",
        data=csrf_form(),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/apps/{app_id}"

    resp2 = await client.get(f"/apps/{app_id}", cookies={SESSION_COOKIE_NAME: token})
    assert resp2.status_code == 200
    assert "revoked" in resp2.text


async def test_cross_app_revoke_ui_404(client: AsyncClient, admin_auth_header: dict) -> None:
    """A key id from another app cannot be revoked via this app's route."""
    app_a_resp = await client.post(
        "/api/v1/apps", json={"name": "Cross Revoke App A"}, headers=admin_auth_header
    )
    app_a_id = app_a_resp.json()["id"]
    app_b_resp = await client.post(
        "/api/v1/apps", json={"name": "Cross Revoke App B"}, headers=admin_auth_header
    )
    app_b_id = app_b_resp.json()["id"]
    app_a_key_id = (await keys.list_keys(app_a_id))[0]["id"]

    token = _get_session_cookie()
    resp = await client.post(
        f"/apps/{app_b_id}/keys/{app_a_key_id}/revoke",
        data=csrf_form(),
        cookies={SESSION_COOKIE_NAME: token},
        follow_redirects=False,
    )
    assert resp.status_code == 404


async def test_ui_create_app_key_unknown_app_404(client):
    """Minting against a nonexistent app hit the FK constraint and 500'd."""
    await client.post("/login", data={"username": "admin", "password": "testpassword"})
    page = await client.get("/settings")
    import re

    token = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
    response = await client.post(
        "/apps/does-not-exist/keys",
        data={"label": "x", "scopes": ["emails:read"], "csrf_token": token},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cookie Secure flag — derived from base_url (code review 2026-07-27)
# ---------------------------------------------------------------------------


async def test_cookies_not_secure_over_plain_http(client, monkeypatch):
    """A Secure cookie on an http:// deployment is dropped by the browser and
    would lock the admin out of the UI entirely."""
    from seesee.config import settings

    monkeypatch.setattr(settings, "base_url", "http://localhost:8080")
    response = await client.post("/login", data={"username": "admin", "password": "testpassword"})
    assert response.status_code == 303
    assert "secure" not in response.headers["set-cookie"].lower()


async def test_cookies_secure_over_https(client, monkeypatch):
    from seesee.config import settings

    monkeypatch.setattr(settings, "base_url", "https://seesee.example.com")
    response = await client.post("/login", data={"username": "admin", "password": "testpassword"})
    assert response.status_code == 303
    assert "secure" in response.headers["set-cookie"].lower()


async def test_flash_cookie_carrying_a_plaintext_key_is_secure_over_https(monkeypatch):
    """The flash cookie briefly holds a plaintext API key — it must not travel
    in the clear on an HTTPS deployment.

    Uses its own https:// client: a Secure cookie is not stored by a client on
    a plain-http origin, so the shared fixture could never stay logged in here.
    """
    import re

    from httpx import ASGITransport, AsyncClient

    from seesee.config import settings
    from seesee.main import app

    monkeypatch.setattr(settings, "base_url", "https://seesee.example.com")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://seesee.example.com"
    ) as https_client:
        await https_client.post("/login", data={"username": "admin", "password": "testpassword"})
        page = await https_client.get("/settings")
        token = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
        response = await https_client.post(
            "/settings/keys",
            data={
                "label": "agent",
                "scopes": ["apps:read"],
                "expires": "90",
                "csrf_token": token,
            },
        )
        assert response.status_code == 303
        flash = [c for c in response.headers.get_list("set-cookie") if "seesee_flash" in c]
        assert flash, "minting a key should set the flash cookie"
        assert "secure" in flash[0].lower()
