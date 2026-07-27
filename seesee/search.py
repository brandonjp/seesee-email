"""FTS5 query normalization.

SQLite's FTS5 `MATCH` operand is a query *language*, not a literal string, so
ordinary user input crashes it: `user@example.com`, a stray `"`, or a lone `(`
all raise `sqlite3.OperationalError` and surface as a 500. Every search path
(REST, UI, MCP) routes its `q` through `normalize_fts_query` first.

Policy — try the raw query, fall back to quoted terms:

1. The query is offered to FTS5 as-is. Well-formed input keeps working exactly
   as before, including the advanced syntax (`subject:hello`, `foo AND bar`,
   `reset*`, `"exact phrase"`) that power users may already rely on.
2. If FTS5 rejects it, each alphanumeric run is re-emitted as a quoted phrase
   (`user@example.com` -> `"user" "example" "com"`), which is always valid.
3. If the input holds no searchable term at all (`((((`, `***`, whitespace),
   there is nothing to match — the caller is told to return zero results
   rather than to run an unfiltered query.
"""

import re
import sqlite3

# A "term" is a run of word characters minus underscore — the same shape FTS5's
# default (unicode61) tokenizer produces, so quoting these can never re-introduce
# a syntax error.
_TERM_RE = re.compile(r"[^\W_]+", re.UNICODE)


def quote_fts_terms(query: str) -> str | None:
    """Rewrite arbitrary text as a conjunction of quoted FTS5 phrases.

    Returns None when the input contains no searchable term.
    """
    terms = _TERM_RE.findall(query)
    if not terms:
        return None
    return " ".join(f'"{term}"' for term in terms)


async def normalize_fts_query(db, query: str) -> str | None:
    """Return an FTS5 MATCH expression guaranteed to parse, or None.

    None means "this query can never match anything" — callers must return an
    empty result set instead of dropping the search condition, which would
    otherwise widen the query to every row.
    """
    if not query or not query.strip():
        return None
    try:
        await db.execute("SELECT rowid FROM emails_fts WHERE emails_fts MATCH ? LIMIT 1", (query,))
    except sqlite3.OperationalError:
        return quote_fts_terms(query)
    return query
