"""Tests for authentication — API keys, SMTP credentials, slug generation."""

from seesee.auth import (
    API_KEY_PREFIX,
    generate_api_key,
    generate_slug,
    hash_secret,
    verify_secret,
)


def test_api_key_has_prefix():
    """Generated API keys start with ss_ prefix."""
    key = generate_api_key()
    assert key.startswith(API_KEY_PREFIX)


def test_api_key_sufficient_length():
    """Generated API keys are long enough for security."""
    key = generate_api_key()
    assert len(key) > 20


def test_api_key_unique():
    """Each generated API key is unique."""
    keys = {generate_api_key() for _ in range(10)}
    assert len(keys) == 10


def test_hash_and_verify_roundtrip():
    """Hashing then verifying with the same secret returns True."""
    secret = "ss_test_secret_12345"
    hashed = hash_secret(secret)
    assert verify_secret(secret, hashed)


def test_verify_wrong_secret():
    """Verifying with a wrong secret returns False."""
    hashed = hash_secret("correct_secret")
    assert not verify_secret("wrong_secret", hashed)


def test_slug_simple():
    """Simple name produces lowercase hyphenated slug."""
    assert generate_slug("BookLink.fyi") == "booklink-fyi"


def test_slug_spaces_and_special_chars():
    """Spaces and special characters are replaced with hyphens."""
    assert generate_slug("My Cool  App!") == "my-cool-app"


def test_slug_leading_trailing_stripped():
    """Leading and trailing non-alphanumeric characters are stripped."""
    assert generate_slug("  --Test App--  ") == "test-app"


def test_slug_unicode_normalized():
    """Unicode characters are normalized to ASCII equivalents."""
    assert generate_slug("Café App") == "cafe-app"


def test_slug_empty_fallback():
    """Empty or all-special-char names fall back to 'app'."""
    assert generate_slug("!!!") == "app"
    assert generate_slug("") == "app"
