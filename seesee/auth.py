"""Authentication utilities for API keys, SMTP credentials, and UI sessions.

API keys are prefixed with `ss_` and stored as bcrypt hashes.
Session auth uses secure signed cookies via itsdangerous.
"""

import secrets
import bcrypt

API_KEY_PREFIX = "ss_"
API_KEY_LENGTH = 32


def generate_api_key() -> str:
    """Generate a new API key with the `ss_` prefix."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(API_KEY_LENGTH)}"


def hash_secret(plaintext: str) -> str:
    """Hash a plaintext secret (API key or SMTP password) with bcrypt."""
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()


def verify_secret(plaintext: str, hashed: str) -> bool:
    """Verify a plaintext secret against its bcrypt hash."""
    return bcrypt.checkpw(plaintext.encode(), hashed.encode())


def generate_smtp_password() -> str:
    """Generate a random SMTP password."""
    return secrets.token_urlsafe(API_KEY_LENGTH)
