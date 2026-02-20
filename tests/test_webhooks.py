"""Tests for POST /api/v1/webhooks/{provider} — provider webhook receivers."""

import base64
import hashlib
import hmac
import json
import time

from httpx import AsyncClient

from seesee.config import settings
from tests.conftest import create_test_app


async def _create_email_with_provider(
    client: AsyncClient,
    admin_auth_header: dict,
    provider: str = "resend",
    provider_message_id: str = "msg_abc123",
) -> tuple[str, str]:
    """Helper: create an app and log an email with provider info. Returns (email_id, api_key)."""
    app_data = await create_test_app(client, admin_auth_header)
    api_key = app_data["api_key"]
    resp = await client.post(
        "/api/v1/log",
        json={
            "to": ["user@example.com"],
            "from": "sender@example.com",
            "subject": "Webhook test email",
            "status": "sent",
            "provider": provider,
            "provider_message_id": provider_message_id,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"], api_key


# ---------------------------------------------------------------------------
# Unknown provider → 404
# ---------------------------------------------------------------------------


async def test_unknown_provider_returns_404(client: AsyncClient) -> None:
    """POST to an unsupported provider returns 404."""
    resp = await client.post(
        "/api/v1/webhooks/mailgun",
        content=json.dumps({"test": True}),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 404
    assert "Unknown webhook provider" in resp.json()["error"]


# ---------------------------------------------------------------------------
# Resend webhooks
# ---------------------------------------------------------------------------


async def test_resend_delivered_updates_status(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """Resend email.delivered webhook updates email status to 'delivered'."""
    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="resend", provider_message_id="resend_msg_001"
    )

    payload = {
        "type": "email.delivered",
        "created_at": "2026-01-01T00:00:00.000Z",
        "data": {
            "email_id": "resend_msg_001",
            "from": "sender@example.com",
            "to": ["user@example.com"],
            "subject": "Test",
        },
    }

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 1
    assert data["matched"] == 1
    assert data["events"][0]["email_id"] == email_id
    assert data["events"][0]["new_status"] == "delivered"

    # Verify email status was actually updated
    email_resp = await client.get(
        f"/api/v1/emails/{email_id}",
        headers=admin_auth_header,
    )
    assert email_resp.status_code == 200
    assert email_resp.json()["status"] == "delivered"


async def test_resend_bounced_updates_status(client: AsyncClient, admin_auth_header: dict) -> None:
    """Resend email.bounced webhook updates email status to 'bounced'."""
    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="resend", provider_message_id="resend_msg_002"
    )

    payload = {
        "type": "email.bounced",
        "data": {"email_id": "resend_msg_002"},
    }

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["events"][0]["new_status"] == "bounced"
    assert resp.json()["events"][0]["matched"] is True


async def test_resend_complained_updates_status(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """Resend email.complained webhook updates email status to 'complained'."""
    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="resend", provider_message_id="resend_msg_003"
    )

    payload = {
        "type": "email.complained",
        "data": {"email_id": "resend_msg_003"},
    }

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["events"][0]["new_status"] == "complained"


async def test_resend_no_match_still_200(client: AsyncClient, admin_auth_header: dict) -> None:
    """Resend webhook for an email not in SeeSee still returns 200 with matched=0."""
    payload = {
        "type": "email.delivered",
        "data": {"email_id": "nonexistent_msg_id"},
    }

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 1
    assert data["matched"] == 0
    assert data["events"][0]["matched"] is False


async def test_resend_unknown_event_type(client: AsyncClient) -> None:
    """Resend webhook with an unrecognized event type processes 0 events."""
    payload = {
        "type": "email.opened",
        "data": {"email_id": "some_msg"},
    }

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["processed"] == 0


async def test_resend_signature_verification_valid(
    client: AsyncClient, admin_auth_header: dict, monkeypatch
) -> None:
    """Resend webhook with a valid Svix signature passes verification."""
    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="resend", provider_message_id="resend_sig_001"
    )

    # Configure a webhook secret
    secret_raw = b"test-secret-key-for-hmac-test!!"
    secret_b64 = base64.b64encode(secret_raw).decode()
    webhook_secret = f"whsec_{secret_b64}"
    monkeypatch.setattr(settings, "webhook_secret_resend", webhook_secret)

    payload = {
        "type": "email.delivered",
        "data": {"email_id": "resend_sig_001"},
    }
    body = json.dumps(payload)

    # Generate valid Svix signature
    svix_id = "msg_test123"
    svix_timestamp = str(int(time.time()))
    signed_content = f"{svix_id}.{svix_timestamp}.{body}"
    signature = base64.b64encode(
        hmac.new(secret_raw, signed_content.encode(), hashlib.sha256).digest()
    ).decode()

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=body,
        headers={
            "content-type": "application/json",
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": f"v1,{signature}",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["matched"] == 1


async def test_resend_signature_verification_invalid(client: AsyncClient, monkeypatch) -> None:
    """Resend webhook with an invalid signature returns 401."""
    secret_raw = b"test-secret-key-for-hmac-test!!"
    secret_b64 = base64.b64encode(secret_raw).decode()
    monkeypatch.setattr(settings, "webhook_secret_resend", f"whsec_{secret_b64}")

    payload = {"type": "email.delivered", "data": {"email_id": "test"}}
    body = json.dumps(payload)

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=body,
        headers={
            "content-type": "application/json",
            "svix-id": "msg_test",
            "svix-timestamp": str(int(time.time())),
            "svix-signature": "v1,invalidsignaturehere",
        },
    )
    assert resp.status_code == 401
    assert "Invalid webhook signature" in resp.json()["error"]


async def test_resend_signature_missing_headers(client: AsyncClient, monkeypatch) -> None:
    """Resend webhook with missing Svix headers returns 401 when secret is configured."""
    monkeypatch.setattr(settings, "webhook_secret_resend", "whsec_dGVzdA==")

    payload = {"type": "email.delivered", "data": {"email_id": "test"}}

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 401


async def test_resend_signature_expired_timestamp(client: AsyncClient, monkeypatch) -> None:
    """Resend webhook with expired timestamp returns 401."""
    secret_raw = b"test-secret-key-for-hmac-test!!"
    secret_b64 = base64.b64encode(secret_raw).decode()
    monkeypatch.setattr(settings, "webhook_secret_resend", f"whsec_{secret_b64}")

    payload = {"type": "email.delivered", "data": {"email_id": "test"}}
    body = json.dumps(payload)

    # Use a timestamp from 10 minutes ago (outside 5-minute tolerance)
    old_timestamp = str(int(time.time()) - 600)
    signed_content = f"msg_test.{old_timestamp}.{body}"
    signature = base64.b64encode(
        hmac.new(secret_raw, signed_content.encode(), hashlib.sha256).digest()
    ).decode()

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=body,
        headers={
            "content-type": "application/json",
            "svix-id": "msg_test",
            "svix-timestamp": old_timestamp,
            "svix-signature": f"v1,{signature}",
        },
    )
    assert resp.status_code == 401


async def test_resend_no_secret_skips_verification(
    client: AsyncClient, admin_auth_header: dict, monkeypatch
) -> None:
    """Without a configured secret, Resend webhooks skip signature verification."""
    monkeypatch.setattr(settings, "webhook_secret_resend", "")

    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="resend", provider_message_id="resend_nosec_001"
    )

    payload = {
        "type": "email.delivered",
        "data": {"email_id": "resend_nosec_001"},
    }

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["matched"] == 1


# ---------------------------------------------------------------------------
# SendGrid webhooks
# ---------------------------------------------------------------------------


async def test_sendgrid_delivered_updates_status(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """SendGrid delivered event updates email status to 'delivered'."""
    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="sendgrid", provider_message_id="sg_msg_001"
    )

    payload = [
        {
            "email": "user@example.com",
            "timestamp": 1234567890,
            "event": "delivered",
            "sg_message_id": "sg_msg_001",
        }
    ]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 1
    assert data["matched"] == 1
    assert data["events"][0]["email_id"] == email_id
    assert data["events"][0]["new_status"] == "delivered"


async def test_sendgrid_bounce_updates_status(client: AsyncClient, admin_auth_header: dict) -> None:
    """SendGrid bounce event updates email status to 'bounced'."""
    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="sendgrid", provider_message_id="sg_msg_002"
    )

    payload = [
        {
            "email": "user@example.com",
            "event": "bounce",
            "sg_message_id": "sg_msg_002",
        }
    ]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["events"][0]["new_status"] == "bounced"


async def test_sendgrid_spamreport_updates_status(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """SendGrid spamreport event maps to 'complained'."""
    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="sendgrid", provider_message_id="sg_msg_003"
    )

    payload = [{"event": "spamreport", "sg_message_id": "sg_msg_003"}]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["events"][0]["new_status"] == "complained"


async def test_sendgrid_multiple_events(client: AsyncClient, admin_auth_header: dict) -> None:
    """SendGrid webhook with multiple events processes all of them."""
    email_id_1, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="sendgrid", provider_message_id="sg_multi_001"
    )
    # Create a second app + email
    app_data = await create_test_app(client, admin_auth_header, name="Second App")
    resp = await client.post(
        "/api/v1/log",
        json={
            "to": ["other@example.com"],
            "from": "sender@example.com",
            "subject": "Multi test",
            "provider": "sendgrid",
            "provider_message_id": "sg_multi_002",
        },
        headers={"Authorization": f"Bearer {app_data['api_key']}"},
    )
    assert resp.status_code == 201

    payload = [
        {"event": "delivered", "sg_message_id": "sg_multi_001"},
        {"event": "bounce", "sg_message_id": "sg_multi_002"},
    ]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 2
    assert data["matched"] == 2


async def test_sendgrid_filter_suffix_matching(
    client: AsyncClient, admin_auth_header: dict
) -> None:
    """SendGrid webhook with .filter suffix in sg_message_id still matches."""
    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="sendgrid", provider_message_id="sg_base_id"
    )

    # SendGrid may append filter info to the message ID in webhooks
    payload = [{"event": "delivered", "sg_message_id": "sg_base_id.filter0001.16648.5515E0B88.0"}]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched"] == 1
    assert data["events"][0]["email_id"] == email_id


async def test_sendgrid_token_verification_valid(
    client: AsyncClient, admin_auth_header: dict, monkeypatch
) -> None:
    """SendGrid webhook with valid verification token passes."""
    monkeypatch.setattr(settings, "webhook_secret_sendgrid", "my-sendgrid-secret")

    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="sendgrid", provider_message_id="sg_tok_001"
    )

    payload = [{"event": "delivered", "sg_message_id": "sg_tok_001"}]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid?verification_token=my-sendgrid-secret",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["matched"] == 1


async def test_sendgrid_token_verification_invalid(client: AsyncClient, monkeypatch) -> None:
    """SendGrid webhook with wrong token returns 401."""
    monkeypatch.setattr(settings, "webhook_secret_sendgrid", "my-sendgrid-secret")

    payload = [{"event": "delivered", "sg_message_id": "test"}]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid?verification_token=wrong-token",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 401
    assert "Invalid webhook verification token" in resp.json()["error"]


async def test_sendgrid_token_verification_missing(client: AsyncClient, monkeypatch) -> None:
    """SendGrid webhook without token returns 401 when secret is configured."""
    monkeypatch.setattr(settings, "webhook_secret_sendgrid", "my-sendgrid-secret")

    payload = [{"event": "delivered", "sg_message_id": "test"}]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 401


async def test_sendgrid_no_secret_skips_verification(
    client: AsyncClient, admin_auth_header: dict, monkeypatch
) -> None:
    """Without a configured secret, SendGrid webhooks skip token verification."""
    monkeypatch.setattr(settings, "webhook_secret_sendgrid", "")

    email_id, _ = await _create_email_with_provider(
        client, admin_auth_header, provider="sendgrid", provider_message_id="sg_nosec_001"
    )

    payload = [{"event": "delivered", "sg_message_id": "sg_nosec_001"}]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["matched"] == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_invalid_json_returns_400(client: AsyncClient) -> None:
    """Webhook with invalid JSON body returns 400."""
    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=b"not valid json {{{",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400
    assert "Invalid JSON payload" in resp.json()["error"]


async def test_resend_missing_email_id_in_payload(client: AsyncClient) -> None:
    """Resend webhook with missing data.email_id processes 0 events."""
    payload = {
        "type": "email.delivered",
        "data": {},
    }

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["processed"] == 0


async def test_sendgrid_unknown_event_types_skipped(client: AsyncClient) -> None:
    """SendGrid events with unmapped types (open, click) are silently skipped."""
    payload = [
        {"event": "open", "sg_message_id": "test1"},
        {"event": "click", "sg_message_id": "test2"},
    ]

    resp = await client.post(
        "/api/v1/webhooks/sendgrid",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["processed"] == 0
