"""FTS5 query normalization — arbitrary user input must never 500.

Before seesee/search.py, any query FTS5 could not parse (an email address, a
stray quote, a lone paren) raised sqlite3.OperationalError straight out of the
route. These lock in that (a) well-formed queries keep their existing meaning,
(b) malformed ones degrade to a term search, and (c) a query with no searchable
term matches nothing rather than everything.
"""

import pytest

from seesee.search import quote_fts_terms
from tests.conftest import create_test_app

# Inputs FTS5 rejects outright — all of these used to be a 500.
MALFORMED_QUERIES = ['bar"', "foo(", "-foo", "a:b:c", "user@example.com", "it's"]

# Inputs with no searchable term at all.
NO_TERM_QUERIES = ["((((", "***", '"""', "   ", "~!@#$%^&*()"]


async def _log_email(client, api_key, **overrides):
    payload = {
        "to": ["user@example.com"],
        "from": "noreply@myapp.com",
        "subject": "Password reset",
        "body_text": "Click the reset link",
        **overrides,
    }
    response = await client.post(
        "/api/v1/log", json=payload, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------


def test_quote_fts_terms_splits_on_non_word_characters():
    assert quote_fts_terms("user@example.com") == '"user" "example" "com"'


def test_quote_fts_terms_returns_none_without_terms():
    for query in NO_TERM_QUERIES:
        assert quote_fts_terms(query) is None, query


def test_quote_fts_terms_output_has_no_unbalanced_quotes():
    assert quote_fts_terms('say "hi"') == '"say" "hi"'


# ---------------------------------------------------------------------------
# REST — GET /api/v1/emails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", MALFORMED_QUERIES)
async def test_rest_search_malformed_query_does_not_500(client, admin_auth_header, query):
    app_data = await create_test_app(client, admin_auth_header)
    await _log_email(client, app_data["api_key"])
    response = await client.get("/api/v1/emails", params={"q": query}, headers=admin_auth_header)
    assert response.status_code == 200


async def test_rest_search_email_address_finds_the_email(client, admin_auth_header):
    """The motivating case: searching a recipient address is the obvious thing
    to type into an email log, and it used to crash."""
    app_data = await create_test_app(client, admin_auth_header)
    await _log_email(client, app_data["api_key"])
    response = await client.get(
        "/api/v1/emails", params={"q": "user@example.com"}, headers=admin_auth_header
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.parametrize("query", NO_TERM_QUERIES)
async def test_rest_search_without_terms_matches_nothing(client, admin_auth_header, query):
    """Must not degrade into an unfiltered listing of every email."""
    app_data = await create_test_app(client, admin_auth_header)
    await _log_email(client, app_data["api_key"])
    response = await client.get("/api/v1/emails", params={"q": query}, headers=admin_auth_header)
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_rest_search_well_formed_query_unchanged(client, admin_auth_header):
    """Advanced FTS5 syntax still reaches FTS5 verbatim."""
    app_data = await create_test_app(client, admin_auth_header)
    await _log_email(client, app_data["api_key"])
    for query in ["reset*", '"password reset"', "password AND reset", "subject:password"]:
        response = await client.get(
            "/api/v1/emails", params={"q": query}, headers=admin_auth_header
        )
        assert response.status_code == 200, query
        assert response.json()["total"] == 1, query


# ---------------------------------------------------------------------------
# Bulk delete — a query that cannot match must delete nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", NO_TERM_QUERIES)
async def test_bulk_delete_without_terms_deletes_nothing(client, admin_auth_header, query):
    app_data = await create_test_app(client, admin_auth_header)
    await _log_email(client, app_data["api_key"])
    response = await client.request(
        "DELETE", "/api/v1/emails", params={"q": query}, headers=admin_auth_header
    )
    assert response.status_code == 200
    assert response.json()["deleted"] == 0
    remaining = await client.get("/api/v1/emails", headers=admin_auth_header)
    assert remaining.json()["total"] == 1


async def test_bulk_delete_malformed_query_still_deletes_matches(client, admin_auth_header):
    app_data = await create_test_app(client, admin_auth_header)
    await _log_email(client, app_data["api_key"])
    response = await client.request(
        "DELETE", "/api/v1/emails", params={"q": "user@example.com"}, headers=admin_auth_header
    )
    assert response.status_code == 200
    assert response.json()["deleted"] == 1


# ---------------------------------------------------------------------------
# UI search page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", MALFORMED_QUERIES + NO_TERM_QUERIES)
async def test_ui_search_malformed_query_does_not_500(client, admin_auth_header, query):
    app_data = await create_test_app(client, admin_auth_header)
    await _log_email(client, app_data["api_key"])
    await client.post("/login", data={"username": "admin", "password": "testpassword"})
    response = await client.get("/emails", params={"q": query})
    assert response.status_code == 200
