"""CSRF token tests — unit round-trip now; endpoint enforcement tests below."""

from seesee.csrf import make_csrf_token, validate_csrf_token


def test_csrf_round_trip():
    token = make_csrf_token("admin", "sekrit")
    assert validate_csrf_token(token, "admin", "sekrit", 3600)


def test_csrf_wrong_username_rejected():
    token = make_csrf_token("admin", "sekrit")
    assert not validate_csrf_token(token, "other", "sekrit", 3600)


def test_csrf_wrong_secret_rejected():
    token = make_csrf_token("admin", "sekrit")
    assert not validate_csrf_token(token, "admin", "different", 3600)


def test_csrf_garbage_rejected():
    assert not validate_csrf_token("not-a-token", "admin", "sekrit", 3600)
