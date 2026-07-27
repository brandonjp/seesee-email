# Management API Keys + MCP Server — Design

**Date:** 2026-07-26 (revised 2026-07-27)
**Status:** Approved — revised per adversarial review (`2026-07-26-management-keys-mcp-review.md`); all blocking edits B1–B5 and required fixes N1, N2 applied, plus adopted recommendations (CSRF hoisted to its own spec, `created_by` column, 90-day UI expiry default, lazy legacy fallback, `TOOL_SCOPES` single source of truth, guarded `last_used_at` UPDATE, verified MCP SDK surface)
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
- Management keys: `ss_mgmt_`-prefixed, labeled, scoped, optionally expiring, individually revocable, with `created_by` provenance.
- A five-scope vocabulary enforced across REST, SMTP, and MCP, with a normative kind/scope validity matrix.
- Multi-key-per-app, enabling safe (non-destructive) rotation.
- MCP server mounted at `/mcp`, covering provisioning and email debugging (SDK surface verified against `mcp==1.26.0`; see §6).
- UI for creating and revoking both key kinds.
- CSRF tokens on session-authenticated UI form POSTs — **shipped as its own spec, run first**, so the new key forms are born protected (see "CSRF" and "Implementation order").
- CLI for headless bootstrap of the first management key.

Out of scope:

- Multi-user auth or roles (`ROADMAP.md:156`) — the admin password remains the single human identity.
- Per-app-scoped management keys (an `app_ids` binding). Additive later via a nullable column; no use case today, since the primary operation is *creating* apps.
- An audit-log table. `last_used_at` + `created_by` answer the questions that matter ("is this key still in use?", "which keys did a leaked key mint?") without inventing a log-retention problem.
- Dropping the now-vestigial `apps.api_key` / `apps.smtp_password` columns — deferred one release for rollback safety, with an explicit transition-release write policy (see §1a).
- Management keys minting other management keys. Deliberately excluded; see "Bootstrap".

## Background — current state

- **Keys:** `seesee/auth.py` generates `ss_` + 32 bytes urlsafe, bcrypt-hashed. `apps.key_prefix` stores the first 8 chars of the random segment for O(1) candidate lookup, then bcrypt-verifies (`seesee/dependencies.py:45-56`).
- **SMTP password is the API key.** `smtp_server.py:107` verifies the supplied SMTP password against `app_row["api_key"]`. `create_app` writes the same bcrypt hash into both `api_key` and `smtp_password` (`routes/apps.py:79`). Any multi-key design must decide what SMTP auth means — see "SMTP" below.
- **The SMTP authenticator is sync by hard constraint.** `SmtpAuthenticator.__call__` must be a plain sync callable — aiosmtpd invokes it without awaiting, and the last violation of this rule silently passed all auth and broke ingest for months (documented at `smtp_server.py:63-75`, fixed in v0.19.13). Every design decision touching SMTP auth must respect this.
- **Integration payload already exists.** `ui.py:65` `_build_env_vars()` renders the complete `.env` block (API key, SMTP host/port/username/password, base URL, app ID and log URLs). The MCP `create_app` tool reuses it verbatim rather than reinventing the format. Note `_build_env_vars` emits the key **twice** — `MAIL_SEESEE_API_KEY` and `MAIL_SEESEE_SMTP_PASSWORD` (`ui.py:75,81`).
- **Migrations** are sequential `if current_version < N` blocks in `database.py:_run_migrations()`, each guarded by a `PRAGMA table_info` existence check. Current `SCHEMA_VERSION = 3`. **Fresh databases never run migrations:** `init_db` stamps `schema_version = SCHEMA_VERSION` via `INSERT OR IGNORE` *before* `_run_migrations()` runs (`database.py:130-137`), so on a fresh database the version is born at the current value and every migration block is skipped. Anything a migration creates must therefore also exist in `SCHEMA_SQL`.
- **CSRF is a known gap** (`ROADMAP.md:154`), currently accepted for single-admin self-hosted use. The session cookie is already `SameSite=Lax` (`ui.py:177`), which blocks the classic cross-site form POST in modern browsers; CSRF tokens are defense in depth, not the sole barrier.

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
    created_by   TEXT NOT NULL,              -- 'admin' | 'cli' | 'migration' | key id that minted it
    expires_at   DATETIME,
    last_used_at DATETIME,
    revoked_at   DATETIME,
    created_at   DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_app_id ON api_keys(app_id);
```

`app_id IS NULL` distinguishes a management key from an app key. `key_prefix` is the first 8 characters of the random segment (excluding the `ss_` / `ss_mgmt_` marker), matching today's extraction logic so the lookup path is unchanged.

`created_by` is the minimum viable provenance: `'admin'` (minted via UI), `'cli'` (bootstrap CLI), `'migration'` (v4 backfill), or the `api_keys.id` of the management key that minted it (REST/MCP mint). Without it, "a management key leaked — which keys did it mint during the window?" is unanswerable; `last_used_at` says a key is alive, not where it came from.

**All datetime columns use the project's existing UTC `%Y-%m-%dT%H:%M:%S` string format**, so lexicographic comparison in SQL is valid (`expires_at < now`, debounce bounds). This codebase has already had one timezone-format-consistency campaign; do not start a second.

Token formats:

- App key: `ss_<43 urlsafe chars>` — unchanged, existing keys remain valid.
- Management key: `ss_mgmt_<43 urlsafe chars>`.

**Prefix extraction is ambiguous by construction and must be handled explicitly.** `ss_mgmt_` starts with `ss_`, and `secrets.token_urlsafe` can emit a random segment that itself begins `mgmt_`. A token is therefore not a reliable signal of its own kind. Two consequences:

1. `extract_prefix` tries the longer marker first and, when a token matches both, returns *both* candidate slices. It returns no candidates (→ 401) for tokens shorter than marker + 8 chars. `resolve_key` looks up candidates for each slice and bcrypt-verifies against all matches.
2. **The database row, never the token, determines whether a key is a management key** — `app_id IS NULL` is authoritative. Nothing in the auth path may branch on the token's textual prefix. Ever.

**`SCHEMA_SQL` gains the `api_keys` table and both indexes.** This is not optional: fresh databases never run migrations (see Background), so a build that only adds the migration block ships a broken fresh install. Consequently `create_app` (and every other mint path) writes `api_keys` rows directly — the migration backfill only ever runs for databases upgrading from ≤3.

**Migration v4** backfills one `api_keys` row per existing app as a **single statement**:

```sql
INSERT INTO api_keys (id, key_hash, key_prefix, label, app_id, scopes, created_by, created_at)
SELECT lower(hex(randomblob(16))), a.api_key, COALESCE(a.key_prefix, ''), 'default', a.id,
       '["emails:read","emails:write"]', 'migration', a.created_at
FROM apps a
WHERE NOT EXISTS (SELECT 1 FROM api_keys k WHERE k.app_id = a.id);
```

Properties, all load-bearing — do not "simplify" any of them away:

- **Idempotent per app** via the `NOT EXISTS` guard: re-running never duplicates and never clobbers keys minted after the migration. This also covers the crash window between the block's commit and the version stamp.
- **Single statement**: SQLite serializes writers, so two new containers racing the migration during a Coolify deploy overlap cannot interleave per-row inserts. A Python loop of per-row inserts has neither property.
- **NULL `key_prefix` rows** (near-hypothetical — `key_prefix` has existed since the first feature commit) migrate with an empty-string prefix rather than being skipped: such a key cannot authenticate over REST today (no prefix to look up) but **does** work over SMTP (username lookup, no prefix involved), and skipping the row would regress SMTP. Empty prefix preserves exactly today's behavior: SMTP works, REST doesn't.

Every key in the wild keeps working with byte-identical permissions.

### 1a. Legacy-column write policy for 0.20.0 (transition release)

`apps.api_key` and `apps.smtp_password` are `NOT NULL`, so 0.20.0 **must** write something to them, and what it writes determines what a rollback to 0.19.x does. The policy, explicitly:

- **Dual-write the app's primary key lifecycle.** `create_app` and the legacy `POST /rotate-key` write the real bcrypt hash to both `api_keys` and `apps.api_key`/`apps.smtp_password`. An app created or rotated under 0.20.0 therefore still authenticates after a rollback.
- **Tombstone on revoke.** Revoking the key whose hash mirrors `apps.api_key` (the "primary" key — in practice: any revoke where the key row's hash equals the app row's `api_key`) also overwrites both legacy columns with a tombstone — the bcrypt hash of a freshly generated random value nobody holds. Rollback then cannot resurrect a revoked credential; a key revoked *because it leaked* stays dead even on 0.19.x.
- **Multi-key mints exist only in `api_keys`.** Keys minted via the new `POST .../keys` path are not mirrored, and are documented as lost on rollback to 0.19.x (the app's primary key still works). Management keys likewise exist only in `api_keys` and do not survive rollback — acceptable, since no 0.19.x surface consumes them.
- **Lazy fallback self-heals deploy-overlap orphans.** During a rolling deploy, an old 0.19.x container can create an app *after* the new container ran the backfill; that app has `apps.api_key` but no `api_keys` row. Therefore, for 0.20.0 only: if no `api_keys` candidate verifies, `resolve_key` falls back to the `apps` table lookup (by prefix for REST; the SMTP resolver's username lookup covers SMTP), verifies against `apps.api_key`, and **on success lazily inserts the missing `api_keys` row** — the request carries the plaintext, so even a NULL prefix is computed correctly at that moment. The fallback and the dual-write both get deleted in 0.21.0 along with the columns.

### 2. Scopes

Five scopes, fixed vocabulary:

| Scope | Grants |
|---|---|
| `emails:read` | Search and read emails |
| `emails:write` | Ingest emails (what app keys do today) |
| `apps:read` | List and read app records and key metadata |
| `apps:write` | Create/update apps, mint and revoke app keys |
| `apps:delete` | Delete apps, purge emails |

**Kind/scope validity matrix — enforced server-side at mint time (REST, MCP, UI, and CLI all route through the same `create_key` validation), not just in the UI:**

| Key kind | Valid scopes |
|---|---|
| App key (`app_id` set) | `emails:read`, `emails:write` only |
| Management key (`app_id` NULL) | `emails:read`, `apps:read`, `apps:write`, `apps:delete` |

Minting an app-bound key with any `apps:*` scope is a 422 — this closes the escalation where an `apps:write` holder mints an app key carrying `apps:write`/`apps:delete`. `emails:write` on a management key is invalid (ingest requires an app-bound key via `get_current_app`), so the combination is rejected rather than silently meaningless.

Scope checks are enforced at the dependency layer for REST and at tool-dispatch for MCP. An app key's scopes are additionally hard-bound to its own `app_id` — the existing behavior of `require_admin_or_app` (`dependencies.py:191`), preserved.

`apps:delete` is **not** in the default set the UI pre-selects when minting a management key. It must be ticked explicitly, with a warning. The obvious path to "give my agent a key" therefore yields a credential that can provision and read but cannot destroy.

**`apps:write` is transitively near-admin, and the docs must say so from day one.** A key holding only `apps:write` can mint an `emails:read`+`emails:write` key for every app, so it transitively grants read/write of all email in the instance. The scope vocabulary is a one-way door; publishing this property now prevents anyone later claiming the scopes promised an isolation they never provided. The UI scope description and the docs-site page state it plainly.

### 3. Key resolution — `seesee/keys.py`

One new module owning the key lifecycle, so the logic lives in exactly one place instead of being spread across `auth.py`, `dependencies.py`, and `smtp_server.py`.

**The module is split into sync and async layers by hard constraint** (the SMTP authenticator cannot await — see Background):

```python
@dataclass(frozen=True)
class Principal:
    key_id: str
    app_id: str | None      # None = management key
    scopes: frozenset[str]
    label: str

# --- Pure sync helpers (no I/O; shared by both resolvers) ---
def generate_key(management: bool = False) -> str: ...
def extract_prefix(token: str) -> list[str]: ...        # 0, 1, or 2 candidate slices; [] for too-short tokens
def verify_key_row(token: str, row: Mapping) -> bool: ...  # bcrypt verify + revoked/expired predicate
def key_is_active(row: Mapping, now: str) -> bool: ...     # revoked_at IS NULL and (expires_at IS NULL or > now)

# --- Async (aiosqlite) — REST and MCP ---
async def resolve_key(token: str) -> Principal | None: ...
async def create_key(*, label, app_id, scopes, expires_at, created_by) -> tuple[str, str]:  # (key_id, plaintext); validates the kind/scope matrix, raises ValueError on violation
async def revoke_key(key_id: str) -> bool: ...
async def list_keys(app_id: str | None) -> list[dict]: ...   # metadata only, never hashes

# --- Sync (stdlib sqlite3) — SMTP authenticator only ---
def resolve_smtp_password(smtp_username: str, password: str) -> bool: ...
```

`resolve_key` performs: prefix extraction → candidate lookup by `key_prefix` → bcrypt verify → reject if `revoked_at IS NOT NULL` → reject if `expires_at` is in the past → legacy `apps` fallback if nothing verified (§1a, 0.20.0 only) → record use → return `Principal`.

`resolve_smtp_password` mirrors today's sync pattern (`smtp_server.py` already uses stdlib `sqlite3`): look up the app by `smtp_username`, fetch all active `api_keys` rows for that app carrying `emails:write`, bcrypt-verify the supplied password against each, with the §1a legacy fallback. It shares the pure helpers with the async path so the two resolvers cannot drift.

**`last_used_at` is debounced to at most one write per key per 60 seconds, via a single guarded UPDATE** (not read-compare-write — no race to reason about, and it stays correct when the SMTP thread's sync connection becomes a second writer):

```sql
UPDATE api_keys SET last_used_at = :now
WHERE id = :key_id AND (last_used_at IS NULL OR last_used_at < :now_minus_60s)
```

The SMTP path updates `last_used_at` too, same statement, via its sync connection — this introduces the first write on the SMTP thread's connection, so that connection sets `busy_timeout`.

bcrypt cost per request is unchanged from today — one hash comparison per candidate prefix match (REST), K comparisons for an app with K active keys (SMTP). Future work, noted so nobody builds it now: `resolve_key` being the single choke point makes an opt-in verified-token cache (SHA-256 of token → key_id, short TTL, invalidated on revoke) a ~20-line change if ingest volume ever demands it.

### 4. Auth integration

Rewired onto `resolve_key` / `resolve_smtp_password`, preserving external behavior:

- `dependencies.get_current_app` — resolves the Bearer token, requires an app key (`app_id is not None`) with `emails:write`, and **returns the full app row exactly as today** (ingest needs `body_storage_mode` etc.) — the rewire adds the app-row fetch after resolution; the return contract is unchanged.
- `dependencies.require_admin_or_app` — unchanged precedence (session cookie → Basic → Bearer), now returning a `Principal` for the Bearer branch. Its session-cookie acceptance remains what it is today: a read-only convenience on `GET /api/v1/emails`.
- `smtp_server` `AUTH` handler — calls `resolve_smtp_password`; a supplied password matching **any non-revoked, non-expired `emails:write` key for that app** authenticates. This is what makes safe rotation work over SMTP as well as REST. The authenticator remains a plain sync callable.
- **New:** `dependencies.require_scope(*scopes)` — a dependency factory returning a `Principal`. **Accepts exactly two credential forms: a management-key Bearer token, or HTTP Basic admin (which implicitly holds all scopes). It never reads the session cookie.** A cookie-authenticated state-changing API route would be an ambient-credential CSRF surface that the UI-form CSRF work does not cover; no state-changing API route accepts cookies today, and none may start now. UI forms post to `ui.py` handlers (session + CSRF protected) which share service-layer code with the API routes. Raises 401 on a missing/unresolvable key, 403 (naming the required scope) on a resolved key missing the scope. App-bound keys resolved by `require_scope` are rejected 403 for `apps:*` scopes by the validity matrix (they can never hold them).

### 5. REST surface

New endpoints:

| Method | Path | Scope |
|---|---|---|
| `GET` | `/api/v1/apps/{id}` | `apps:read` |
| `GET` | `/api/v1/apps/{id}/keys` | `apps:read` |
| `POST` | `/api/v1/apps/{id}/keys` | `apps:write` |
| `DELETE` | `/api/v1/apps/{id}/keys/{key_id}` | `apps:write` |

`GET .../keys` returns metadata only — `id`, `label`, `key_prefix`, `scopes`, `created_by`, `created_at`, `last_used_at`, `expires_at`, `revoked_at`. Never a hash, never a plaintext.

`POST .../keys` validates the kind/scope matrix (app-bound keys: `emails:read`/`emails:write` only; violations 422) and records `created_by` = the minting principal (`'admin'` for Basic auth, the management key's id for Bearer).

**`DELETE .../keys/{key_id}` returns 404 unless the key's `app_id` matches the path's `{id}`.** Revocation by bare `key_id` would let an `apps:write` management key revoke *management* keys (including the admin's other keys) — a lockout/DoS violating the rule that management keys cannot touch management keys. There is deliberately no REST route that revokes a management key; that remains UI/CLI only.

Existing `/api/v1/apps` routes gain management-key auth alongside admin auth, mapped to scopes: `POST` and `PATCH` require `apps:write`, `GET` requires `apps:read`, both `DELETE` routes require `apps:delete`.

**Existing email endpoints are not rewired in 0.20.0.** A management key with `emails:read` reads email over MCP (the agent surface), not over `GET /api/v1/emails` — that route keeps its current auth (`require_admin_or_app`). This is a deliberate scoping decision, not an oversight; widening the REST email surface to management keys is additive later if a use case appears.

**Safe rotation** is now expressible: `POST .../keys` to mint → deploy the new value → `DELETE .../keys/{old_id}` to revoke. The legacy `POST /api/v1/apps/{id}/rotate-key` keeps its current immediate-invalidation semantics for backwards compatibility (including the §1a dual-write); its docstring and the docs site point at the two-step path as preferred.

### 6. MCP server — `seesee/mcp_server.py`

FastMCP (the official `mcp` Python SDK) mounted into the existing FastAPI app at `/mcp`, gated by `SEESEE_MCP_ENABLED` (default `true`). Authentication is the same `Authorization: Bearer ss_mgmt_…` header resolved by the same `resolve_key` — MCP is a new transport over existing authorization, not a new authorization system.

Client setup is one command:

```
claude mcp add --transport http seesee https://seesee.example.com/mcp \
  --header "Authorization: Bearer ss_mgmt_..."
```

#### Verified SDK surface (`mcp==1.26.0`, verified 2026-07-27 by a running end-to-end experiment)

The following facts were confirmed against the installed SDK, not inferred. Pin `mcp>=1.26,<2` and implement exactly this shape:

- **Construction:** `FastMCP(name, stateless_http=True, json_response=True, streamable_http_path="/")`. `stateless_http=True` makes every POST self-contained (no session persistence — which is what makes per-request auth sound). `streamable_http_path` defaults to `"/mcp"`, so mounting the app at `/mcp` without overriding it yields `/mcp/mcp` — override to `"/"`.
- **Mounting:** `app.mount("/mcp", <auth middleware>(mcp.streamable_http_app()))`. `streamable_http_app()` returns a Starlette app.
- **Lifespan:** the parent FastAPI lifespan must run `async with mcp.session_manager.run():` — without it every request 500s. Compose with the existing lifespan in `seesee/main.py`.
- **Trailing slash:** Starlette's `Mount` 307-redirects `POST /mcp` → `/mcp/`, and MCP clients cannot be assumed to follow redirects on POST. Add a tiny pure-ASGI middleware (registered on the FastAPI app) that rewrites `scope["path"] == "/mcp"` to `"/mcp/"`. Verified: both URL forms then return 200.
- **Transport security:** leave `transport_security` unset. The SDK's `TransportSecurityMiddleware` disables DNS-rebinding Host/Origin validation when no settings are passed (verified in source) — correct for an internet-facing, reverse-proxied deployment where our own Bearer auth is the gate. Do **not** pass `TransportSecuritySettings()` explicitly: its field default flips protection **on** with an empty allowlist, which rejects every request.
- **Scope filtering and dispatch:** subclass FastMCP; the subclass overrides the **public** `list_tools()` and `call_tool()` methods (FastMCP registers exactly these as the protocol handlers — verified in `_setup_handlers`). No private API.
- **Principal plumbing:** the auth middleware stores the resolved `Principal` in a `contextvars.ContextVar`; tool handlers and the two overrides read it. Verified: the contextvar set in ASGI middleware propagates through the SDK session manager's task spawns into tool execution under `stateless_http=True`.
- **Dispatch-denial shape:** an exception raised in the `call_tool` override surfaces to the client as a tool result with `isError: true` carrying the message — acceptable and verified; no custom JSON-RPC error plumbing needed.
- **`session_manager.run()` is once-per-instance** (verified in source: it raises `RuntimeError` on re-entry). Therefore `seesee/mcp_server.py` exposes a `create_mcp_server()` factory rather than only a module-level singleton — `main.py` builds one instance at import; tests build a fresh instance (and run its own `session_manager`) per test.

#### Auth — normative

- **The `/mcp` mount is wrapped in a pure-ASGI auth middleware that runs before any SDK code parses the request body.** The SDK is the newest, least-audited code in the process and must not parse unauthenticated bytes. The middleware: extracts the Bearer token → `resolve_key` → 401 (`"Invalid or missing API key"` / `"API key revoked"` / `"API key expired"`) on failure.
- **Any principal with `app_id IS NOT NULL` is rejected 401 before dispatch, regardless of scopes.** Migrated app keys hold `emails:read`; if MCP checked scopes only, an app key could read *every* app's email over `/mcp` — a cross-tenant read app keys have never had. The row decides kind (never the token prefix); the check is on the resolved principal.
- **The principal is resolved per request, never cached for an MCP session.** `stateless_http=True` makes this the natural shape; the constraint is stated anyway so nobody reintroduces session-scoped auth with a stateful transport later. Revocation therefore takes effect on the next request.

#### Tools

**One module-level `TOOL_SCOPES: dict[str, str]` is the single source of truth** driving both the `tools/list` filter and the dispatch check; a test asserts every registered tool has exactly one entry. Two independently maintained scope maps would drift; one map makes drift impossible.

Tools are filtered by the caller's scopes at `tools/list` — a key holding only `emails:read` does not see `create_app` at all, rather than seeing it and failing on call.

| Tool | Scope | Returns |
|---|---|---|
| `create_app` | `apps:write` | App record + plaintext key + the `_build_env_vars()` block |
| `create_app_key` | `apps:write` | New key plaintext + metadata |
| `revoke_app_key` | `apps:write` | Confirmation (same belongs-to-app rule as REST: unknown/mismatched key → error, never cross-kind revocation) |
| `list_apps` | `apps:read` | App records (no credentials) |
| `get_app` | `apps:read` | Single app record + key metadata |
| `get_integration_env` | `apps:read` | `_build_env_vars()` with the key redacted to a placeholder |
| `search_emails` | `emails:read` | Matching emails (FTS5, honors existing search semantics) |
| `get_email` | `emails:read` | Full email record, subject to `body_storage_mode` and degradation |
| `list_recent_failures` | `emails:read` | Recent emails with `status='failed'` + `error_message` |

**Deliberately absent: `delete_app` and `purge_emails`, even for a key holding `apps:delete`.** The MCP caller is definitionally an LLM agent consuming attacker-influenceable email content; destruction stays off that surface, via UI or an explicit REST call. The REST/MCP asymmetry is a feature. Also absent: any key-minting tool for management keys (see "Bootstrap").

`get_integration_env` redacts the key because the plaintext is unrecoverable after creation — returning a placeholder is honest, whereas returning a partial or fabricated value is not. **Pass the placeholder as the `api_key` argument to `_build_env_vars()`** — the block emits the key twice (`MAIL_SEESEE_API_KEY`, `MAIL_SEESEE_SMTP_PASSWORD`) and substituting the argument redacts both; hand-reconstructing the block would miss the second occurrence.

**Docs guidance (prompt injection):** `search_emails` / `get_email` / `list_recent_failures` feed attacker-influenceable text (subjects, bodies, webhook `error_message`) into an agent that may also hold minting tools. The docs page recommends splitting credentials: a read-only key (`emails:read` + `apps:read`) for debugging agents, a separate `apps:write` key for provisioning agents — not one key with everything.

### 7. UI

**Settings → "API Keys"** section:

- Table of management keys: label, `ss_mgmt_…` prefix, scopes, created by, last used, expires, revoke action.
- Create form: label (required), scope checkboxes (management-valid scopes only — no `emails:write`, per the validity matrix), expiry select (30 / 90 / 365 days / never), **defaulting to 90 days**. Agents are the credential class most likely to be pasted into a config file and forgotten; "never" stays one click away, but the inherited-by-strangers default expires. `apps:delete` renders unchecked with an inline warning describing its blast radius; the `apps:write` description states plainly that it transitively grants access to all email (§2).
- Plaintext shown exactly once via the existing `_set_flash` pattern (`ui.py:573`).

**App detail page** gains an equivalent per-app keys table with mint and revoke (app-valid scopes only: `emails:read`/`emails:write`), replacing rotate-key as the recommended path. The existing rotate button stays, relabeled to make its destructive nature explicit.

All new forms are session-authenticated POSTs to `ui.py` handlers and therefore carry CSRF tokens from birth (the CSRF spec lands first — see "Implementation order").

### 8. CSRF

Session-authenticated UI form POSTs currently carry no CSRF token (`ROADMAP.md:154`). The session cookie is already `SameSite=Lax`, which blocks the classic cross-site form POST in modern browsers — so this is defense in depth against the residual (older browsers, subdomain-hosted attacker content), not the sole barrier. It still matters more after this release than before it: a forged request against the key-creation form would mint a durable, scoped, attacker-known credential that survives password changes and is invisible until someone reads the key list.

- Signed CSRF token derived from the session secret (`itsdangerous`, already a dependency), embedded as a hidden field.
- Validated on every session-authenticated `POST` handler in `ui.py`.
- Bearer-authenticated REST and MCP are unaffected — **which is true only because `require_scope` never accepts the session cookie (§4)**; no ambient credential reaches any state-changing API route.

**CSRF ships as its own spec, ordered first** (see "Implementation order"): it shares no code with the keys work, its `test_ui.py` churn lands in isolation, and every new key-management form is born protected instead of retrofitted.

### 9. Bootstrap and CLI

The first management key must be obtainable without a browser (headless Docker, CI):

```
python -m seesee.keys create --label ci --scopes apps:write,emails:read [--expires-days N]
```

Writes directly to the database (`created_by='cli'`), prints the plaintext once to stdout, validates the scope matrix like every other mint path. Companion `list` and `revoke` subcommands for recovery. CLI-minted keys default to no expiry unless `--expires-days` is given — operators bootstrapping CI know what they want; the 90-day nudge is a UI default only.

**Management keys cannot mint or revoke management keys** — no `keys:write` scope exists, no REST endpoint, no MCP tool. The principle: **keep the delegation graph at depth 1, with both roots of trust (admin password via UI, database access via CLI) human-held, so every machine credential is at most one revocation away from a human.** The one level of delegation that does exist (management keys minting app keys) is auditable via `created_by`. This is a deliberate constraint, not an omission.

### 10. Config

New settings in `seesee/config.py`:

- `mcp_enabled: bool = True` → `SEESEE_MCP_ENABLED`

Reuses existing `base_url` and `smtp_port` for the integration env block.

## Error handling

- Missing/malformed `Authorization` → 401, `WWW-Authenticate: Bearer`.
- Resolvable key, insufficient scope → 403 naming the required scope.
- Revoked or expired key → 401 with a distinct detail message (`"API key revoked"` / `"API key expired"`), so an operator can tell the two apart from logs. The marginal information leak (confirming a dead key once existed) is worth the operability.
- Mint request violating the kind/scope matrix → 422 naming the invalid scope(s).
- MCP errors surface as MCP protocol errors carrying the same messages; missing/invalid auth is a plain HTTP 401 from the middleware (never reaches the SDK); a dispatch-time scope denial surfaces as an `isError` tool result.
- Migration failure leaves `schema_version` unchanged so the next boot retries; the backfill is idempotent (§1).

## Testing

New:

- `tests/test_api_keys.py` — generation and prefix extraction for both formats (including too-short tokens → no candidates, and dual-candidate `ss_mgmt_`/`mgmt_`-random-segment ambiguity); bcrypt verify; revoked rejected; expired rejected; scope enforcement per endpoint; kind/scope matrix rejections (app key with `apps:write` → 422; management key with `emails:write` → 422); cross-key revoke: `DELETE /apps/{id}/keys/{key_id}` 404s when the key belongs to another app or is a management key; `require_scope` never authenticates via session cookie (explicit test: cookie-bearing request to a `require_scope` route → 401); `last_used_at` debounce (two rapid calls produce one write, guarded-UPDATE form); metadata endpoints never leak hashes; `created_by` recorded correctly per mint path.
- `tests/test_migration_v4.py` — a database seeded at v3 with an app migrates such that the pre-existing key still authenticates over both REST and SMTP; migration is idempotent across two runs; NULL-`key_prefix` row migrates with empty prefix and still authenticates over SMTP; a fresh database (born at v4 via `SCHEMA_SQL`) has the `api_keys` table and `create_app` writes rows to it; §1a dual-write: rotate under v4 updates legacy columns; revoke of the primary key tombstones them; lazy fallback: an `apps`-only orphan row authenticates once and gains an `api_keys` row.
- `tests/test_mcp.py` — `tools/list` filtered by scope; every registered tool has exactly one `TOOL_SCOPES` entry; `create_app` round-trip returning a usable key; 401 on missing, revoked, and app-key principals (regardless of scopes); revocation effective on the next request (no session caching); `delete_app` absent regardless of scope; both `POST /mcp` and `POST /mcp/` work; `get_integration_env` redacts both key occurrences; disabled via `SEESEE_MCP_ENABLED=false` → 404.
- `tests/test_csrf.py` — session POST without a token rejected; with a valid token accepted; Bearer REST unaffected.

- `tests/test_smtp_keys.py` — multi-key SMTP auth (a second minted key authenticates) and revoked-key rejection. A **new** file, deliberately: `test_smtp.py` and `test_smtp_integration.py` are frozen under the regression bar below, so the new SMTP behavior gets its own file rather than an "extension" that would breach the freeze.

**Regression bar (restated per review N1):** the **entire existing test suite passes** in every spec. Additionally, per spec (see "Implementation order"):

- **CSRF spec:** only `test_ui.py` may be modified, and only by adding CSRF-token plumbing through a shared helper/fixture — assertions and expected status codes unchanged. Checkable by diff.
- **Foundation spec:** no existing test file is modified. `test_smtp_integration.py` is explicitly frozen — it is the wire-level suite (real `Controller` + `smtplib`) that caught the async-authenticator bug and the only end-to-end exercise of the SMTP auth path this spec rewires. `test_apps.py`, `test_auth.py`, `test_ingest.py`, `test_smtp.py`, `test_batch_ingest.py`, `test_status_update.py`, `test_delete.py`, `test_search.py`, `test_email_detail.py` all ride on the rewired dependencies and are equally protected by the no-modification rule.
- **REST/UI spec:** no existing test file is modified except `test_ui.py`, which may gain (not alter) assertions for the new key forms.
- **MCP spec:** no existing test file is modified.

Any edit outside those budgets means backwards compatibility was broken and the change needs rework, not the test.

## Implementation order

Four sequential Ralph specs, dependency-ordered. Do not merge them into one loop; the auth foundation must be verified correct before anything sits on it.

1. **CSRF** (hoisted per review N9) — tokens on all existing session POST handlers. Small, isolated, lands the noisy `test_ui.py` churn alone, and every form added later is born protected.
2. **Foundation** — schema v4 + `SCHEMA_SQL`, `seesee/keys.py` (sync/async split), migration + backfill, §1a dual-write/tombstone/lazy-fallback, rewire `get_current_app` / `require_admin_or_app` / SMTP auth, CLI bootstrap.
3. **REST + scopes + UI** — `require_scope`, management/app key endpoints, kind/scope matrix enforcement, Keys UI (born CSRF-protected).
4. **MCP server** — `/mcp` mount per the verified SDK surface, auth middleware, `TOOL_SCOPES`, the nine tools.

## Rollout

Version 0.20.0 — minor, additive, no breaking API changes. `apps.api_key` and `apps.smtp_password` retained under the §1a write policy; the columns, the dual-write, and the lazy fallback are all removed together in 0.21.0.

Documentation: new docs-site page covering management keys and MCP setup (including the read-only-vs-provisioning key split and the `apps:write` transitivity note); README section; CHANGELOG entry; `ROADMAP.md:154` (CSRF) marked complete.

## Open risks

- **`/mcp` is internet-facing** on every instance with the default config. Mitigated by the pre-SDK auth middleware rejecting unauthenticated bytes, per-request resolution, and the `SEESEE_MCP_ENABLED` off switch. Worth a prominent note in the docs.
- **`get_email` returns body content to an agent.** That is the point of the debugging tools, but email bodies can contain reset tokens and PII. The tool respects existing `body_storage_mode` and degradation rules — it does not bypass them — and the docs say plainly that granting `emails:read` grants the agent access to email contents (and recommend the split-credential pattern, §6).
- **The `mcp` SDK is a new runtime dependency** in the server process. Pinned `>=1.26,<2`; the mounting surface, auth path, and filtering mechanics are verified against 1.26.0 (§6). If the SDK proves unstable the JSON-RPC surface is small enough to hand-roll, at the cost of owning it permanently.
