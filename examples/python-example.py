"""SeeSee — Python integration example.

Log sent emails to your SeeSee instance after sending via any provider.
"""

import httpx

SEESEE_URL = "https://seesee.example.com"
SEESEE_KEY = "ss_your_api_key_here"


def log_email(
    to: str | list[str],
    subject: str,
    body_text: str,
    *,
    from_addr: str = "noreply@example.com",
    provider: str = "resend",
    status: str = "sent",
    **kwargs,
) -> None:
    """Log a sent email to SeeSee."""
    httpx.post(
        f"{SEESEE_URL}/api/v1/log",
        headers={"Authorization": f"Bearer {SEESEE_KEY}"},
        json={
            "to": to if isinstance(to, list) else [to],
            "from": from_addr,
            "subject": subject,
            "body_text": body_text,
            "status": status,
            "provider": provider,
            **kwargs,
        },
        timeout=5,
    )


# Usage:
# log_email("user@example.com", "Welcome!", "Thanks for signing up.")
