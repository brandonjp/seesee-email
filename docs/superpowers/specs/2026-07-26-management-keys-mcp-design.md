# Management API Keys + MCP Server — Design

**Date:** 2026-07-26
**Status:** Approved
**Target version:** 0.20.0
**Topic:** Give agents and automation a first-class, scoped, revocable credential for managing a SeeSee instance, and expose provisioning + email-debugging over MCP.

## Problem

A developer running SeeSee at `seesee.example.com` wants their coding agent (Claude Code, or any MCP client) to register new apps and retrieve the credentials needed to integrate them, without a human copying values out of a browser.

The REST endpoints for this already exist (`seesee/routes/apps.py`) and return everything needed — `POST /api/v1/apps` responds with the app's `api_key` (which doubles as the SMTP password, see `seesee/smtp_server.py:107`) and `smtp_username`. The blocker is the **credential the agent authenticates with**, and three structural gaps behind it:

1. **No machine credential.** Every management route is `Depends(require_admin)` — HTTP Basic against the single `ADMIN_USERNAME` / `ADMIN_PASSWORD` (`seesee/dependencies.py:70`). Handing that to an agent hands over the web UI login and full destructive access. Revoking it means changing the global admin password and breaking every other consumer.
2. **No scopes.** Admin is all-or-nothing globally; an app key is all-or-nothing for its app. There is no read-only credential, and no way to grant "can provision apps" without also granting "can delete apps and all their email."
3. **Destructive rotate.** `apps.api_key` is a single column (`seesee/database.py:32`). `POST /api/v1/apps/{id}/rotate-key` overwrites it, invalidating the old key instantly with no overlap window — rotating a key breaks the running app until it is redeployed. There is no revoke short of rotate-or-delete, and no key metadata (label, expiry, last-used) to reason about.

## Scope

In scope:

- Unified `api_keys` table (schema v4) replacing `apps.api_key` as the source of truth for verification, covering both app keys and management keys.
- Management keys: `ss_mgmt_`-prefixed, labeled, scoped, optionally expiring, individually revocable.
- A five-scope vocabulary enforced across REST, SMTP, and MCP.
- Multi-key-per-app, enabling safe (non-destructive) rotation.
- MCP server mounted at `/mcp`, covering provisioning and email debugging.
- UI for creating and revoking both key kinds.
- CSRF tokens on session-authenticated UI form POSTs (see "CSRF" below for why this is not deferrable).
- CLI for headless bootstrap of the first management key.

Out of scope:

- Multi-user auth or roles (`ROADMAP.md:156`) — the admin password remains the single human identity.
- Per-app-scoped management keys (an `app_ids` binding). Additive later via a nullable column; no use case today, since the primary operation is *creating* apps.
- An audit-log table. `last_used_at` answers the question that matters ("is this key still in use?") without inventing a log-retention problem.
- Dropping the now-vestigial `apps.api_key` / `apps.smtp_password` columns — deferred one release for rollback safety.
- Management keys minting other management keys. Deliberately excluded; see "Bootstrap".

## Background — current state

- **Keys:** `seesee/auth.py` generates `ss_` + 32 bytes urlsafe, bcrypt-hashed. `apps.key_prefix` stores the first 8 chars of the random segment for O(1) candidate lookup, then bcrypt-verifies (`seesee/dependencies.py:45-56`).
- **SMTP password is the API key.** `smtp_server.py:107` verifies the supplied SMTP password against `app_row["api_key"]`. `create_app` writes the same bcrypt hash into both `api_key` and `smtp_password` (`routes/apps.py:79`). Any multi-key design must decide what SMTP auth means — see "SMTP" below.
- **Integration payload already exists.** `ui.py:65` `_build_env_vars()` renders the complete `.env` block (API key, SMTP host/port/username/password, base URL, app ID and log URLs). The MCP `create_app` tool reuses it verbatim rather than reinventing the format.
- **Migrations** are sequential `if current_version < N` blocks in `database.py:_run_migrations()`, each guarded by a `PRAGMA table_info` existence check. Current `SCHEMA_VERSION = 3`.
- **CSRF is a known gap** (`ROADMAP.md:154`), currently accepted for single-admin self-hosted use.

## Design

### 1. Data model — schema v4

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id           TEXT PRIMARY KEY,
    key_hash     TEXT NOT NULL,
    key_prefix   TEXT NOT NULL,
    label        TEXT NOT NULL,
    app_id       TEXT REFERENCES apps(id),   -- NULL = management key
    scopes       TEXT NOT NULL,              -- JSON array of scope strings
    expires_at   DATETIME,
    last_used_at DATETIME,
    revoked_at   DATETIME,
    created_at   DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_app_id ON api_keys(app_id);
```

`app_id IS NULL` distinguishes a management key from an app key. `key_prefix` is the first 8 characters of the random segment (excluding the `ss_` / `ss_mgmt_` marker), matching today's extraction logic so the lookup path is unchanged.

Token formats:

- App key: `ss_<43 urlsafe chars>` — unchanged, existing keys remain valid.
- Management key: `ss_mgmt_<43 urlsafe chars>`.

**Prefix extraction is ambiguous by construction and must be handled explicitly.** `ss_mgmt_` starts with `ss_`, and `secrets.token_urlsafe` can emit a random segment that itself begins `mgmt_`. A token is therefore not a reliable signal of its own kind. Two consequences:

1. `extract_prefix` tries the longer marker first and, when a token matches both, returns *both* candidate slices. `resolve_key` looks up candidates for each and bcrypt-verifies against all matches.
2. **The database row, never the token, determines whether a key is a management key** — `app_id IS NULL` is authoritative. Nothing in the auth path may infer privilege from the token's textual prefix.

**Migration v4** inserts one `api_keys` row per existing app:

```
id=uuid4, key_hash=apps.api_key, key_prefix=apps.key_prefix,
label='default', app_id=apps.id,
scopes='["emails:read","emails:write"]',
created_at=apps.created_at, expires_at=NULL, revoked_at=NULL
```

Idempotent per app — the insert selects only apps with no existing `api_keys` row (`WHERE NOT EXISTS (SELECT 1 FROM api_keys k WHERE k.app_id = apps.id)`), so re-running never duplicates and never clobbers keys minted after the migration. Apps whose `key_prefix` is NULL (rows predating that column) are skipped and logged as a warning rather than migrated with a broken lookup key. Every key in the wild keeps working with byte-identical permissions. `apps.api_key` and `apps.smtp_password` are left populated but stop being read after this migration.

### 2. Scopes

Five scopes, fixed vocabulary:

| Scope | Grants |
|---|---|
| `emails:read` | Search and read emails |
| `emails:write` | Ingest emails (what app keys do today) |
| `apps:read` | List and read app records and key metadata |
| `apps:write` | Create/update apps, mint and revoke app keys |
| `apps:delete` | Delete apps, purge emails |

Scope checks are enforced at the dependency layer for REST and at tool-dispatch for MCP. An app key's scopes are additionally hard-bound to its own `app_id` — the existing behavior of `require_admin_or_app` (`dependencies.py:191`), preserved.

`apps:delete` is **not** in the default set the UI pre-selects when minting a management key. It must be ticked explicitly, with a warning. The obvious path to "give my agent a key" therefore yields a credential that can provision and read but cannot destroy.

### 3. Key resolution — `seesee/keys.py`

One new module owning the key lifecycle, so the logic lives in exactly one place instead of being spread across `auth.py`, `dependencies.py`, and `smtp_server.py`.

```python
@dataclass(frozen=True)
class Principal:
    key_id: str
    app_id: str | None      # None = management key
    scopes: frozenset[str]
    label: str

def generate_key(management: bool = False) -> str: ...
def extract_prefix(token: str) -> str | None: ...
async def resolve_key(token: str) -> Principal | None: ...
async def create_key(*, label, app_id, scopes, expires_at) -> tuple[str, str]:  # (key_id, plaintext)
async def revoke_key(key_id: str) -> bool: ...
async def list_keys(app_id: str | None) -> list[dict]: ...   # metadata only, never hashes
```

`resolve_key` performs: prefix extraction → candidate lookup by `key_prefix` → bcrypt verify → reject if `revoked_at IS NOT NULL` → reject if `expires_at` is in the past → record use → return `Principal`.

**`last_used_at` is debounced to at most one write per key per 60 seconds.** Without this, every ingest request becomes a SQLite write; on a WAL database under ingest load that is a measurable regression, not a theoretical one. The debounce is a compare against the currently stored value before issuing the `UPDATE`.

bcrypt cost per request is unchanged from today — one hash comparison per candidate prefix match.

### 4. Auth integration

Rewired onto `resolve_key`, preserving external behavior:

- `dependencies.get_current_app` — resolves the Bearer token, requires an app key (`app_id is not None`) with `emails:write`, returns the app row as before.
- `dependencies.require_admin_or_app` — unchanged precedence (session cookie → Basic → Bearer), now returning a `Principal` for the Bearer branch.
- `smtp_server` `AUTH` handler — looks up the app by `smtp_username`, then verifies the supplied password against **any non-revoked, non-expired key for that app** carrying `emails:write`. This is what makes safe rotation work over SMTP as well as REST.
- **New:** `dependencies.require_scope(*scopes)` — a dependency factory returning a `Principal`, accepting either a management key Bearer token or admin auth (session/Basic, which implicitly holds all scopes). Raises 401 on an unresolvable key, 403 on a resolved key missing the scope.

### 5. REST surface

New endpoints:

| Method | Path | Scope |
|---|---|---|
| `GET` | `/api/v1/apps/{id}` | `apps:read` |
| `GET` | `/api/v1/apps/{id}/keys` | `apps:read` |
| `POST` | `/api/v1/apps/{id}/keys` | `apps:write` |
| `DELETE` | `/api/v1/apps/{id}/keys/{key_id}` | `apps:write` |

`GET .../keys` returns metadata only — `id`, `label`, `key_prefix`, `scopes`, `created_at`, `last_used_at`, `expires_at`, `revoked_at`. Never a hash, never a plaintext.

Existing `/api/v1/apps` routes gain management-key auth alongside admin auth, mapped to scopes: `POST` and `PATCH` require `apps:write`, `GET` requires `apps:read`, both `DELETE` routes require `apps:delete`.

**Safe rotation** is now expressible: `POST .../keys` to mint → deploy the new value → `DELETE .../keys/{old_id}` to revoke. The legacy `POST /api/v1/apps/{id}/rotate-key` keeps its current immediate-invalidation semantics for backwards compatibility; its docstring and the docs site point at the two-step path as preferred.

### 6. MCP server — `seesee/mcp_server.py`

FastMCP (the `mcp` Python SDK) mounted into the existing FastAPI app at `/mcp`, gated by `SEESEE_MCP_ENABLED` (default `true`). Authentication is the same `Authorization: Bearer ss_mgmt_…` header resolved by the same `resolve_key` — MCP is a new transport over existing authorization, not a new authorization system.

Client setup is one command:

```
claude mcp add --transport http seesee https://seesee.example.com/mcp \
  --header "Authorization: Bearer ss_mgmt_..."
```

**Tools are filtered by the caller's scopes at `tools/list`.** A key holding only `emails:read` does not see `create_app` at all, rather than seeing it and failing on call.

| Tool | Scope | Returns |
|---|---|---|
| `create_app` | `apps:write` | App record + plaintext key + the `_build_env_vars()` block |
| `create_app_key` | `apps:write` | New key plaintext + metadata |
| `revoke_app_key` | `apps:write` | Confirmation |
| `list_apps` | `apps:read` | App records (no credentials) |
| `get_app` | `apps:read` | Single app record + key metadata |
| `get_integration_env` | `apps:read` | `_build_env_vars()` with the key redacted to a placeholder |
| `search_emails` | `emails:read` | Matching emails (FTS5, honors existing search semantics) |
| `get_email` | `emails:read` | Full email record, subject to `body_storage_mode` and degradation |
| `list_recent_failures` | `emails:read` | Recent emails with `status='failed'` + `error_message` |

**Deliberately absent: `delete_app` and `purge_emails`, even for a key holding `apps:delete`.** Destruction remains a human action via UI or an explicit REST call. Also absent: any key-minting tool for management keys (see "Bootstrap").

`get_integration_env` redacts the key because the plaintext is unrecoverable after creation — returning a placeholder is honest, whereas returning a partial or fabricated value is not.

### 7. UI

**Settings → "API Keys"** section:

- Table of management keys: label, `ss_mgmt_…` prefix, scopes, last used, expires, revoke action.
- Create form: label (required), scope checkboxes, expiry select (30 / 90 / 365 days / never, defaulting to never). `apps:delete` renders unchecked with an inline warning describing its blast radius.
- Plaintext shown exactly once via the existing `_set_flash` pattern (`ui.py:573`).

**App detail page** gains an equivalent per-app keys table with mint and revoke, replacing rotate-key as the recommended path. The existing rotate button stays, relabeled to make its destructive nature explicit.

### 8. CSRF

Session-authenticated UI form POSTs currently carry no CSRF token (`ROADMAP.md:154`). Today the worst outcome of a forged request is an unwanted key rotation — disruptive, self-evident, recoverable.

After this change, the same gap on the key-creation form lets an attacker mint a **durable, scoped, attacker-known credential** that survives password changes and is invisible until someone reads the key list. That is a different class of problem, so CSRF protection is in scope here rather than deferred:

- Signed CSRF token derived from the session secret (`itsdangerous`, already a dependency), embedded as a hidden field.
- Validated on every session-authenticated `POST` handler in `ui.py`.
- Bearer-authenticated REST and MCP are unaffected — no ambient credential, no CSRF exposure.

### 9. Bootstrap and CLI

The first management key must be obtainable without a browser (headless Docker, CI):

```
python -m seesee.keys create --label ci --scopes apps:write,emails:read [--expires-days N]
```

Writes directly to the database, prints the plaintext once to stdout. Companion `list` and `revoke` subcommands for recovery.

**Management keys cannot mint or revoke management keys** — no `keys:write` scope exists, no REST endpoint, no MCP tool. A key that can mint keys is effectively unrevocable: revoking it does not revoke whatever it already issued. The admin password (via UI) and direct database access (via CLI) remain the only roots of trust for minting. This is a deliberate constraint, not an omission.

### 10. Config

New settings in `seesee/config.py`:

- `mcp_enabled: bool = True` → `SEESEE_MCP_ENABLED`

Reuses existing `base_url` and `smtp_port` for the integration env block.

## Error handling

- Missing/malformed `Authorization` → 401, `WWW-Authenticate: Bearer`.
- Resolvable key, insufficient scope → 403 naming the required scope.
- Revoked or expired key → 401 with a distinct detail message (`"API key revoked"` / `"API key expired"`), so an operator can tell the two apart from logs.
- MCP errors surface as MCP protocol errors carrying the same messages; a missing key yields an empty tool list plus an explanatory error rather than a silent success.
- Migration failure leaves `schema_version` unchanged so the next boot retries; the insert is idempotent.

## Testing

New:

- `tests/test_api_keys.py` — generation and prefix extraction for both formats; bcrypt verify; revoked rejected; expired rejected; scope enforcement per endpoint; `last_used_at` debounce (two rapid calls produce one write); metadata endpoints never leak hashes.
- `tests/test_migration_v4.py` — a database seeded at v3 with an app migrates such that the pre-existing key still authenticates over both REST and SMTP; migration is idempotent across two runs.
- `tests/test_mcp.py` — `tools/list` filtered by scope; `create_app` round-trip returning a usable key; 401 on missing, revoked, and app-key-instead-of-management-key; `delete_app` absent regardless of scope.
- `tests/test_csrf.py` — session POST without a token rejected; with a valid token accepted; Bearer REST unaffected.

Extended: `tests/test_smtp.py` gains multi-key auth and revoked-key rejection.

**Regression bar: `test_apps.py`, `test_auth.py`, `test_ingest.py`, and `test_smtp.py` must pass unmodified.** Any edit required to those files means backwards compatibility was broken and the migration needs rework.

## Rollout

Version 0.20.0 — minor, additive, no breaking API changes. `apps.api_key` and `apps.smtp_password` retained but unread, scheduled for removal in 0.21.0.

Documentation: new docs-site page covering management keys and MCP setup; README section; CHANGELOG entry; `ROADMAP.md:154` (CSRF) marked complete.

## Open risks

- **`/mcp` is internet-facing** on every instance with the default config. Mitigated by rejecting unauthenticated and unscoped requests identically to REST, and by the `SEESEE_MCP_ENABLED` off switch. Worth a prominent note in the docs.
- **`get_email` returns body content to an agent.** That is the point of the debugging tools, but email bodies can contain reset tokens and PII. The tool respects existing `body_storage_mode` and degradation rules — it does not bypass them — and the docs should say plainly that granting `emails:read` grants the agent access to email contents.
- **The `mcp` SDK is a new runtime dependency** in the server process. Pinned with a floor version; if it proves unstable the JSON-RPC surface is small enough to hand-roll, at the cost of owning it permanently.
