# Management API Keys + MCP Server — Adversarial Design Review

**Date:** 2026-07-26
**Reviewing:** `2026-07-26-management-keys-mcp-design.md` (commit `5003a0f`)
**Reviewer:** Fable 5 (second-opinion review, pre-implementation)
**Method:** Every claim in the spec was checked against the actual code on this branch (`auth.py`, `dependencies.py`, `database.py`, `smtp_server.py`, `routes/apps.py`, `routes/ui.py`, `main.py`, `config.py`, tests, git history), not taken on trust.

## Verdict

**Ship with changes.** The core architecture is sound: the unified `api_keys` table is the right shape, the row-is-authority answer to the prefix ambiguity genuinely holds (bcrypt over the full token is the authenticator; the prefix is only a lookup index, so dual-candidate lookup fully resolves the `ss_mgmt_` superstring problem), and the three-spec decomposition is correctly ordered. But the spec has five gaps that an autonomous implementation loop would walk straight through — one of them a direct self-contradiction in the spec's own security reasoning (`require_scope` accepts session cookies while the CSRF section claims Bearer-authenticated REST has "no ambient credential"), and one that makes rollback resurrect revoked credentials. None require redesign; all require the spec text to change before Ralph runs.

## Blocking issues

These must be fixed in the spec before implementation. Each is a specific failure, not a style preference.

### B1. `require_scope` accepts session cookies — the spec's own CSRF claim is false as written

Section 4 defines `require_scope` as "accepting either a management key Bearer token or admin auth (session/Basic, which implicitly holds all scopes)." Section 8 then claims "Bearer-authenticated REST and MCP are unaffected — no ambient credential, no CSRF exposure."

Both cannot be true. If `require_scope` accepts the session cookie, then `POST /api/v1/apps/{id}/keys` and every other state-changing `/api/v1` route it guards is reachable with an ambient credential — exactly the forged-request-mints-a-durable-key scenario the spec's CSRF section exists to prevent, on endpoints the CSRF plan does not cover (it covers only `ui.py` form handlers).

**Failure:** admin visits a malicious page while logged in; a cross-site request hits `POST /api/v1/apps/{id}/keys` with the session cookie; attacker obtains a durable key. The CSRF work in spec 2 would not stop it because these are API routes, not UI form posts.

**Fix:** `require_scope` accepts Bearer (management key) and HTTP Basic only — never the session cookie. UI forms post to `ui.py` handlers (which are session + CSRF protected) and share service-layer code with the API routes. This matches the existing precedent: `require_admin_or_app` added session-cookie acceptance only for a GET (`/api/v1/emails`); no state-changing API route accepts cookies today, and none should start now. (SameSite=Lax on the session cookie — `ui.py:177` — mitigates but does not excuse this; Basic-auth replay and older-browser behavior remain, and the spec should not ship a claim its own definition falsifies.)

### B2. Legacy-column write policy is unspecified — rollback resurrects revoked keys, and `NOT NULL` forces the issue

The spec says `apps.api_key` / `apps.smtp_password` "are left populated but stop being read" and are "deferred one release for rollback safety." It never says whether they stop being **written**, and the schema forces an answer: `apps.api_key` is `TEXT NOT NULL` (`database.py:32`), so `create_app` in 0.20.0 *must* write something there or the INSERT fails.

Unspecified consequences an implementer will resolve arbitrarily:

- **Revocation undone by rollback.** If 0.20.0 revokes/rotates only in `api_keys` and leaves `apps.api_key` holding the old hash, rolling back to a 0.19.x image resurrects every key revoked during 0.20.0 — including a key revoked *because it leaked*. That converts "rollback safety" into a security regression.
- **New apps broken by rollback.** If `create_app` writes a dummy into `apps.api_key`, apps created under 0.20.0 stop authenticating after rollback (REST and SMTP), silently.

**Fix:** the spec must state the transition-release write policy explicitly. Recommended: during 0.20.0, dual-write the app's *primary* key lifecycle — `create_app` and legacy `rotate-key` write the real hash to both `api_keys` and `apps.api_key`/`smtp_password`; revoking the key that mirrors `apps.api_key` also overwrites the legacy columns with a tombstone hash (e.g. a hash of a random value nobody holds), so rollback cannot resurrect it. Keys minted via the new multi-key path exist only in `api_keys` and are documented as lost on rollback. Whatever policy is chosen, it must be written down — this is precisely the kind of decision an autonomous loop resolves by coin-flip.

### B3. No scope-validity matrix — `apps:write` can escalate through minted keys

The spec never constrains which scopes are valid on which key kind. Three concrete holes:

1. **Minted app-key scopes are unconstrained.** `POST /api/v1/apps/{id}/keys` (scope `apps:write`) presumably accepts a `scopes` field. Nothing forbids minting an app-bound key carrying `apps:write` or `apps:delete`. Whether that escalates depends on unwritten details of how `require_scope` treats app-key principals — a security boundary should not depend on unwritten details.
2. **Cross-key revocation is unconstrained.** `DELETE /api/v1/apps/{id}/keys/{key_id}` — the spec does not require `key_id` to belong to app `{id}`. An implementation that revokes by `key_id` alone lets a management key with `apps:write` revoke *management* keys (including the admin's other keys) — violating the spec's own rule that management keys cannot revoke management keys, and enabling a lockout/DoS.
3. **Meaningless combinations render in the UI.** `emails:write` on a management key does nothing (ingest requires an app-bound key via `get_current_app`), but the UI checkbox list as specced would offer it.

**Fix:** add a normative validity matrix — app-bound keys may carry only `emails:read` / `emails:write` (enforced server-side at mint time, not just in the UI); management keys may carry `emails:read`, `apps:read`, `apps:write`, `apps:delete`; `DELETE .../keys/{key_id}` must 404 unless the key's `app_id` matches the path. Add tests for all three.

### B4. MCP's rejection of app-key principals is carried by a test bullet, not the design

Migrated app keys hold `["emails:read","emails:write"]`. The MCP tools `search_emails` / `get_email` require `emails:read`. If MCP dispatch checks *scopes only*, an app key authenticates to `/mcp` and reads **every app's** email — a cross-tenant read that app keys have never had (they are hard-bound to their own `app_id` in `require_admin_or_app`). The only place the spec addresses this is a bullet in the Testing section ("401 on … app-key-instead-of-management-key"). Design-by-test-bullet is exactly what drifts when an autonomous loop rewrites tests to pass.

**Fix:** state normatively in section 6: the MCP endpoint rejects any principal with `app_id IS NOT NULL`, regardless of scopes, before dispatch. Also state that the principal is resolved **per request** (never cached for the MCP session), so revocation takes effect immediately; the `mcp` SDK's HTTP transport is session-oriented and an implementer could plausibly resolve auth once at `initialize`.

### B5. `resolve_key` is async; the SMTP authenticator is sync by hard constraint — the spec's "one module owns the lifecycle" is unimplementable as written

`SmtpAuthenticator.__call__` must be a plain sync callable — aiosmtpd invokes it without awaiting, and the last time this rule was violated, SMTP auth silently passed everything and ingest was broken for months (documented at `smtp_server.py:63-75`, fixed in v0.19.13). Section 3 defines a single `async def resolve_key`; section 4 says the SMTP handler verifies "against any non-revoked, non-expired key for that app." There is no way to call the async resolver from the sync authenticator without event-loop games (the authenticator runs on the SMTP controller's own loop thread — `asyncio.run` there is exactly the kind of hazard that caused the v0.19.13 bug).

**Fix:** the spec must prescribe the split: pure sync helpers in `seesee/keys.py` (prefix extraction, bcrypt verify, revocation/expiry predicate — all take a row, return a bool) shared by `async resolve_key` (aiosqlite, REST/MCP) and a sync `resolve_smtp_password(username, password)` used by the authenticator via stdlib `sqlite3`, mirroring today's pattern. Decide explicitly whether the SMTP path updates `last_used_at` (recommended: yes, same 60s debounce, via the guarded single-statement UPDATE from N6 — it introduces the first write on the SMTP thread's connection, so set `busy_timeout`). Without this, spec 1's Ralph loop will flail on its most safety-critical file.

## Non-blocking concerns

Ordered by significance.

### N1. The regression bar has exactly the hole the question suspected

`test_apps.py`, `test_auth.py`, `test_ingest.py`, `test_smtp.py` unmodified is necessary but not sufficient:

- **`test_smtp_integration.py` is not on the list.** It is the wire-level suite (real `Controller` + `smtplib`) that caught the async-authenticator bug — the only test that exercises the code path B5 changes end-to-end. A loop could modify it freely while breaking real SMTP auth. It must be on the unmodified list for spec 1.
- **`test_batch_ingest.py`, `test_status_update.py`, `test_delete.py`, `test_search.py`, `test_email_detail.py`** all ride on `get_current_app` / `require_admin_or_app`, both rewired in spec 1. Not protected.
- **`test_ui.py` will legitimately need modification** in spec 2 (every session POST needs a CSRF token), which is a loophole: assertions could be weakened under cover of "adding token plumbing."

**Fix:** restate the bar as: *the entire existing suite passes; no existing test file is modified in specs 1 and 3; in spec 2, only `test_ui.py` may change, and only by adding CSRF token plumbing (via a helper/fixture) — assertions and expected status codes unchanged.* That is checkable by diff and closes the walk-through.

### N2. Migration mechanics: the fresh-database path never runs migrations

`init_db` stamps `schema_version = SCHEMA_VERSION` via `INSERT OR IGNORE` *before* `_run_migrations()` runs (`database.py:130-137`). On a fresh database the version is born at 4 and the v4 block is skipped entirely. Therefore: the `api_keys` table (and its two indexes) must also be added to `SCHEMA_SQL`, and `create_app` must write `api_keys` rows directly — the migration backfill only ever runs for databases upgrading from ≤3. The spec doesn't mention `SCHEMA_SQL` at all; a loop that only writes the migration block ships a broken fresh install. Also worth stating: the backfill should be a single `INSERT INTO api_keys … SELECT … FROM apps WHERE NOT EXISTS (…)` statement — SQLite serializes writers, so this is also what makes the two-new-containers-race-the-migration case (Coolify deploy overlap) safe, which a Python loop of per-row inserts is not guaranteed to be. The spec's idempotency claim is correct and is also load-bearing for the crash window between the block's commit and the version stamp — say so, so nobody "simplifies" it away.

### N3. Deploy-overlap orphans, and a lazy fallback that would erase three risks at once

During a rolling deploy, an old (0.19.x) container can create an app *after* the new container ran the backfill. That app has an `apps.api_key` but no `api_keys` row — its key works on the old container and is permanently broken on the new one, with no self-healing. Separately: the spec's handling of NULL-`key_prefix` rows (skip + warn) is wrong-direction — such a row cannot authenticate over REST today, but *does* work over SMTP (username lookup, no prefix involved), so skipping it regresses SMTP. (Mitigating fact from git history: `key_prefix` has existed since the first feature commit, so such rows are near-hypothetical — but the spec explicitly legislates for them, and legislates the regression.)

**Recommended:** for the 0.20.0 release only, keep a fallback in `resolve_key`: if no `api_keys` candidate verifies, look up `apps` by prefix (and SMTP by username, as today) and verify against `apps.api_key`; on success, lazily insert the missing `api_keys` row — the request carries the plaintext, so even a NULL prefix can be computed correctly at that moment. This self-heals both cases and gets deleted in 0.21.0 along with the columns. If the fallback is rejected as too much transitional code, at minimum change the NULL-prefix handling to migrate with an empty-string prefix (SMTP keeps working; REST stays broken-as-today) rather than skip.

### N4. `apps:write` is transitively near-admin — document it, and add `created_by`

A management key holding only `apps:write` can mint an `emails:read` + `emails:write` key for every app, so it transitively grants read/write of all email in the instance. The scope model's apparent separation between "can provision" and "can read email" is porous by design, and the UI warning currently reserved for `apps:delete` under-communicates this. Two cheap responses: (1) the docs and the UI scope descriptions should say plainly that `apps:write` implies eventual access to all email; (2) add a `created_by TEXT` column to `api_keys` (key id, `'admin'`, or `'cli'`). Without it, "a management key leaked; which keys did it mint during the window?" is unanswerable — `last_used_at` tells you a key is alive, not where it came from. This is the single cheapest concession to auditability available, it is additive, and it directly serves the spec's own revocation story.

### N5. `tools/list` filtering: keep it, but force it to share one source of truth with dispatch

Filtering the listing is not security theater — it is real UX for agents (an agent that can't see `create_app` won't waste turns trying it) — but the question's instinct is right that two independently-maintained scope maps will drift. The fix is structural, not vigilance: one module-level `TOOL_SCOPES: dict[str, str]` drives both the list filter and the dispatch check, and a test asserts every registered tool has exactly one entry. With that, drift is impossible rather than unlikely. The spec should mandate it.

### N6. `last_used_at` debounce: replace read-compare-write with a guarded UPDATE

The specced compare-then-write has a benign race (two concurrent requests both see a stale value and both write — a wasted write, not a correctness bug, since the row was already fetched during resolution). But the race and the reasoning about it vanish entirely with a single statement: `UPDATE api_keys SET last_used_at = ? WHERE id = ? AND (last_used_at IS NULL OR last_used_at < ?)` with the 60s-ago cutoff as the bound. Same cost, no read-modify-write, and it's the form that stays correct when the SMTP thread's sync connection (B5) becomes a second writer. Also pin the storage format: `expires_at` / `last_used_at` must use the project's existing UTC `%Y-%m-%dT%H:%M:%S` string format so lexicographic comparison in SQL is valid — this codebase has already had one timezone-format-consistency campaign; don't start a second.

### N7. bcrypt-per-request is a pre-existing cost the spec correctly doesn't worsen — but it centralizes the fix point

The spec's claim checks out: REST ingest already pays one bcrypt verify per request (`dependencies.py:54-56`), prefix lookup still narrows to ~1 candidate (the dual-slice candidates of B-section fame almost never coexist), and SMTP pays K verifies only for an app with K active keys. No regression. Worth one sentence in the spec, though: `resolve_key` becoming the single choke point makes a future opt-in verified-token cache (SHA-256 of token → key_id, short TTL, invalidated on revoke) a 20-line change if ingest volume ever demands it. Note it as future work so nobody builds it now.

### N8. Harden the `/mcp` front door and the redaction detail

- Auth should be checked (401 on missing/unresolvable/app-bound key) in a dependency/middleware *before* the request body reaches the `mcp` SDK's JSON-RPC parsing — the SDK is the newest, least-audited code in the process and shouldn't parse unauthenticated bytes. This also honors the spec's own "empty tool list plus explanatory error" behavior cheaply.
- `get_integration_env` redaction: `_build_env_vars` emits the key **twice** (`MAIL_SEESEE_API_KEY` and `MAIL_SEESEE_SMTP_PASSWORD`, `ui.py:75,81`). Passing the placeholder as the `api_key` argument redacts both — say so explicitly, because an implementer who reconstructs the block by hand will miss the second occurrence.
- Prompt injection: `search_emails` / `get_email` / `list_recent_failures` feed attacker-influenceable text (subjects, bodies, webhook `error_message`) into an agent that also holds minting tools. Server-side there is little to do beyond what the spec already does (no destructive tools, B3's mint constraints), but the docs guidance should be explicit: use a *read-only* key (`emails:read` + `apps:read`) for debugging agents and a separate `apps:write` key for provisioning agents, rather than one key with everything.

### N9. Consider hoisting CSRF, and right-size its urgency

Verified against code: the session cookie is already `SameSite=Lax` (`ui.py:177`), which blocks the classic cross-site form POST in every modern browser. The spec's "not deferrable" framing overstates the live risk — the realistic residual is older browsers and subdomain-hosted attacker content. CSRF is still correct to do (defense in depth, and B1 shows the reasoning matters), but two consequences: (1) it need not gate anything — it could ship as its own small spec *before* the foundation work, which has the pleasant property that the new key-management forms in spec 2 are born CSRF-protected instead of retrofitted, and `test_ui.py` churn lands in isolation; (2) if the schedule tightens, deferring CSRF behind B1's fix (no cookies on state-changing API routes) is a defensible fallback, whereas the spec currently presents it as load-bearing for the key-minting threat — it is only load-bearing if B1 is left unfixed.

### N10. Small spec-text gaps an autonomous loop will otherwise guess at

- Which *existing* email endpoints accept a management key with `emails:read`? As specced, a debugging agent can search email over MCP but gets 401 from `GET /api/v1/emails` REST. Probably fine for 0.20.0 (MCP is the agent surface) — but say so, or the loop will "helpfully" rewire `require_admin_or_app`.
- `extract_prefix` must return `None` (→ 401) for tokens shorter than marker + 8 chars.
- `get_current_app` currently returns the full app row (ingest needs `body_storage_mode` etc.); after rewiring through `resolve_key` it needs a second query or a join to keep returning it. State that the return contract is unchanged.
- Distinct `"API key revoked"` / `"API key expired"` 401 details: fine — the marginal information leak (confirming a dead key once existed) is worth the operability. Agreed as specced.

## Decisions I would have made differently — and those that survived scrutiny

**Survived — unified `api_keys` table.** Separate tables would duplicate lookup, verification, revocation, expiry, and UI for two credential kinds that differ in exactly one bit. The NULL-`app_id` polymorphism is the cost, and B3's validity matrix is the price of paying it safely. Right call.

**Survived — the prefix-ambiguity answer.** I tried to break it and couldn't: bcrypt over the full token string is the sole authenticator; both candidate slices resolve to rows; only the true row verifies; `app_id` on that row decides kind. An app key whose random segment happens to start `mgmt_` is found under its stored prefix via the second candidate slice. The design holds across REST and MCP; SMTP never touches prefixes (username lookup). The one thing to enforce forever: nothing may branch on the token's textual prefix — B4 is where that rule is currently most likely to be violated by accident.

**Survived — HTTP MCP served from the app, not local stdio.** The motivating use case is a remote instance and an agent that may run anywhere; stdio would require every user to install and configure a local proxy holding the key. Serving it from the app with the same auth substrate is less total machinery. The NEXT.md hazard about the unverified SDK mounting surface is real and already correctly flagged — resolve it before spec 3 loops, or run spec 3 interactively.

**Survived — excluding `delete_app`/`purge_emails` from MCP even with `apps:delete`.** The MCP caller is definitionally an LLM agent consuming attacker-influenceable email content (N8); keeping destruction off that surface is the correct asymmetry, and the REST/MCP inconsistency it creates is a feature, not a wart.

**Survived, with corrected reasoning — no management-key minting of management keys.** The conclusion is right; the stated rationale ("a key that can mint keys is effectively unrevocable") proves too much — it applies verbatim to `apps:write` minting app keys, which the spec allows. The real principle is: keep the delegation graph depth 1 and keep both roots of trust (admin password, database access) human-held, so every machine credential is at most one revocation away from a human. Restate it that way, and pair it with N4's `created_by` so the one level of delegation that *does* exist is auditable.

**Would change — expiry defaulting to never.** For a credential aimed at agents — the credential class most likely to be pasted into config files and forgotten — the UI select defaulting to "never" is the wrong nudge. Default the select to 90 days; keep "never" available one click away; CLI keeps requiring explicit `--expires-days` or defaulting to never (operators bootstrapping CI know what they want). No API change, pure default. Cheap, and it's the kind of default strangers running this on the internet inherit silently.

**Would change (narrowly) — `last_used_at` instead of an audit log.** The spec's refusal to invent a log-retention problem is right, and I agree an audit table is out of scope. But `last_used_at` alone cannot answer the post-compromise question its own revocation story creates ("what did the leaked key mint?"). `created_by` (N4) is the minimum viable provenance and I'd treat it as part of this release, not a follow-up.

**Would change — the five-scope vocabulary ships with an unstated asterisk.** The vocabulary itself is fine and I would not add a sixth scope (a hypothetical `keys:mint` split from `apps:write` is useless for the primary use case — registering an app *is* obtaining its credential). But since the vocabulary is a one-way door, the published docs must state the transitive-escalation property of `apps:write` (N4) from day one, so no one later claims the scopes promised an isolation they never provided.

**Decomposition — right split, consider one reorder.** Foundation → REST/UI → MCP is correctly dependency-ordered, and the insistence that the auth foundation be verified before anything sits on it is the most important structural decision in the plan. The one improvement: hoist CSRF out of spec 2 into its own small spec run first (N9). It shares no code with the keys work, its test churn is the noisiest part of spec 2, and landing it first means every new form is born protected.

## Summary of required spec edits

1. B1 — `require_scope`: Bearer + Basic only; session cookies never authenticate state-changing API routes.
2. B2 — explicit legacy-column write policy for 0.20.0 (dual-write primary key; tombstone on revoke; rollback caveats documented).
3. B3 — scope-validity matrix; server-side mint validation; `key_id`-belongs-to-app check on revoke.
4. B4 — MCP rejects app-bound principals normatively; per-request principal resolution.
5. B5 — sync/async resolver split for the SMTP path, with shared pure helpers.
6. N1 — regression bar restated to cover the whole suite, `test_smtp_integration.py` explicitly frozen, `test_ui.py` change budget bounded.
7. N2 — `SCHEMA_SQL` gains `api_keys`; backfill as a single INSERT…SELECT; fresh-DB path acknowledged.

Everything else above is recommended but negotiable.
