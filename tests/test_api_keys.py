"""Tests for seesee.keys — sync core (generation, prefix extraction, scope matrix)."""

import pytest

from seesee.keys import (
    extract_prefix,
    generate_key,
    key_is_active,
    validate_scopes,
)


def test_generate_key_formats():
    app_key = generate_key()
    assert app_key.startswith("ss_")
    assert not app_key.startswith("ss_mgmt_")

    mgmt_key = generate_key(management=True)
    assert mgmt_key.startswith("ss_mgmt_")


def test_extract_prefix_app_key():
    token = "ss_" + "a" * 43
    assert extract_prefix(token) == ["aaaaaaaa"]


def test_extract_prefix_mgmt_key():
    token = "ss_mgmt_" + "b" * 43
    assert extract_prefix(token) == ["b" * 8, "mgmt_bbb"]


def test_extract_prefix_ambiguous_app_key():
    token = "ss_mgmt_xyzabcde" + "c" * 27
    candidates = extract_prefix(token)
    assert len(candidates) == 2
    assert "xyzabcde" in candidates
    assert "mgmt_xyz" in candidates


def test_extract_prefix_too_short():
    assert extract_prefix("ss_abc") == []
    assert extract_prefix("ss_mgmt_ab") == []
    assert extract_prefix("garbage") == []


def test_key_is_active():
    active_row = {"revoked_at": None, "expires_at": None}
    assert key_is_active(active_row, "2026-01-01T00:00:00") == (True, "")

    revoked_row = {"revoked_at": "2026-01-01T00:00:00", "expires_at": None}
    assert key_is_active(revoked_row, "2026-01-02T00:00:00") == (False, "revoked")

    expired_row = {"revoked_at": None, "expires_at": "2020-01-01T00:00:00"}
    assert key_is_active(expired_row, "2026-01-01T00:00:00") == (False, "expired")

    future_row = {"revoked_at": None, "expires_at": "2099-01-01T00:00:00"}
    assert key_is_active(future_row, "2026-01-01T00:00:00") == (True, "")


def test_validate_scopes_matrix():
    # App key: emails scopes OK, apps scopes invalid
    validate_scopes(["emails:read"], "app1")
    with pytest.raises(ValueError):
        validate_scopes(["apps:write"], "app1")

    # Management key: apps scopes OK, emails:write invalid
    validate_scopes(["apps:read", "apps:write"], None)
    with pytest.raises(ValueError):
        validate_scopes(["emails:write"], None)

    # Empty list always invalid
    with pytest.raises(ValueError):
        validate_scopes([], None)
