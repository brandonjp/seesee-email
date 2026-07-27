---
title: MCP Server
description: Let agents provision apps and debug email over the Model Context Protocol
---

## What it is

SeeSee mounts a [Model Context Protocol](https://modelcontextprotocol.io) server at `/mcp` (streamable HTTP transport), letting agents provision apps and debug email delivery without a bespoke integration. It's authenticated by the same `ss_mgmt_` management keys used elsewhere — mint one on **Settings → API Keys** in the web UI, or headlessly:

```bash
python -m seesee.keys create --label "my-agent" --scopes emails:read,apps:read --expires-days 90
```

## Connect Claude Code

```bash
claude mcp add --transport http seesee https://seesee.example.com/mcp --header "Authorization: Bearer ss_mgmt_..."
```

## Tools and scopes

Nine tools, grouped by the scope required to call them:

- **`emails:read`** — `search_emails`, `get_email`, `list_recent_failures`
- **`apps:read`** — `list_apps`, `get_app`, `get_integration_env`
- **`apps:write`** — `create_app`, `create_app_key`, `revoke_app_key`

`tools/list` only returns the tools a key's scopes permit. Destructive operations (deleting an app, purging emails) are deliberately not exposed over MCP — there is no `delete_app` or `purge_emails` tool.

## Security notes

- `/mcp` is internet-facing by default (`SEESEE_MCP_ENABLED=false` disables it).
- Granting `emails:read` grants the agent access to email contents — bodies can contain reset links and PII.
- Email content is untrusted input to your agent — **use a read-only key (`emails:read` + `apps:read`) for debugging agents and a separate `apps:write` key for provisioning agents**.
- `apps:write` transitively grants access to all email (it can mint an `emails:read` key for any app).
- Keys default to 90-day expiry in the UI.
