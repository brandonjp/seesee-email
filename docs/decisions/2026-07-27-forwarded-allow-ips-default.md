# Decision: `SEESEE_FORWARDED_ALLOW_IPS` defaults to private ranges, not `*`

**Date:** 2026-07-27
**Version:** 0.20.3-dev
**Status:** Decided and implemented
**Supersedes:** the `*` default introduced in 0.20.2-dev

## The question

`SEESEE_FORWARDED_ALLOW_IPS` was introduced in 0.20.2-dev with a default of `*`,
and that default was flagged in review as a real trust widening rather than a
detail. Two options were on the table:

1. Keep `*`, and let operators narrow it.
2. Default it to unset (uvicorn's `127.0.0.1`), and make operators widen it.

Neither is good. This decision takes a third option.

## Why the setting exists at all

SeeSee cannot terminate TLS itself — `aiosmtpd` speaks no TLS, so a reverse
proxy in front is not optional, it is the deployment model. That means the app
only knows a request arrived over HTTPS if it trusts the proxy's
`X-Forwarded-Proto`. If it doesn't, `request.url.scheme` stays `http`, and
`cookies_are_secure()` drops the `Secure` flag from the session cookie and the
flash cookie — the latter of which briefly carries a **plaintext API key**.

uvicorn's own default, `forwarded_allow_ips="127.0.0.1"`, never matches a proxy
running in a separate container. Coolify, Docker Compose, and Kubernetes all
connect from a private network address. So the setting has to default to
*something* broader than loopback, or the feature it exists to enable is a
silent no-op in exactly the deployment it was written for.

That rules out option 2. Defaulting to unset doesn't produce a secure system; it
produces a system that is insecure by default and gives no symptom to notice —
no error, no warning at the point of failure, just cookies quietly travelling in
the clear. Correctness that depends on every operator reading a config reference
and acting on it is not correctness.

## Why `*` was not worth keeping either

`*` means any client that can open a TCP connection to SeeSee's HTTP port is
trusted to set forwarding headers. Concretely, on an instance whose app port is
reachable directly (not only through the proxy):

- **`X-Forwarded-For` becomes attacker-controlled.** Every access-log line for
  the attacker's own requests records whatever source address they choose. The
  log stops being an audit trail at the exact moment one would matter.
- **`X-Forwarded-Proto` becomes attacker-controlled**, but this one is close to
  harmless: a forged value only affects the sender's own response, so the worst
  outcome is that they mark their *own* cookie `Secure` or not.

What limits the damage is that **nothing in SeeSee's own code reads the client
IP** — verified by grep across `seesee/` for `request.client`, `client.host`,
`X-Forwarded-For`, and rate-limit code. There is no IP allowlist, no
per-IP rate limiter, no IP-bound session. So the blast radius is log integrity,
not an authentication or rate-limit bypass. That is a real but bounded harm.

It is bounded enough that `*` was defensible. It is not bounded enough to be
worth choosing when a strictly better option exists at no cost.

## The decision

Default to the private ranges a containerized reverse proxy actually connects
from:

```
127.0.0.0/8,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7
```

This works out of the box on every containerized deployment — Coolify, Compose,
and Kubernetes all place the proxy in one of these ranges — while trusting no
public client. `100.64.0.0/10` covers Tailscale and the Kubernetes distributions
that use CGNAT space for pod networking; `fc00::/7` covers IPv6 ULA, which is
what Docker IPv6 and Fly.io use. None of these ranges is routable on the public
internet, so including them does not reintroduce the exposure that `*` created.

`*` remains an accepted value for anyone who wants the old behaviour, and
narrowing further (`SEESEE_FORWARDED_ALLOW_IPS=10.0.1.5`) is better still for
operators who know their proxy's address.

## What this costs

One case regresses: **a proxy that reaches SeeSee from a public address** — a
proxy on a different host with no private network between them. Nothing in the
default list matches it, the forwarded scheme is dropped, and cookies lose their
`Secure` flag.

That case is not left silent. `cookies_are_secure()` checks `SEESEE_BASE_URL`
first and returns true for an `https://` URL regardless of the request scheme,
and `_warn_if_base_url_looks_wrong()` already logs a startup `WARNING` when
`base_url` is `http://` on a non-local host — the exact configuration where this
would bite. The docs-site configuration reference calls the case out explicitly
under its own heading. An operator in this position has both a working fallback
and two places telling them to set the variable.

## The dependency floor this forced

uvicorn only understands CIDR notation in `forwarded_allow_ips` from **0.31.0**.
Verified directly rather than from release notes: downloading 0.30.0, 0.30.6,
0.31.0, 0.32.0, and 0.33.0 and checking `uvicorn/middleware/proxy_headers.py`
shows `_TrustedHosts` and `ipaddress.ip_network` first appearing in 0.31.0.

On 0.30.x, trusted hosts are compared as plain strings. Every CIDR entry above
would match nothing, the trust would narrow to zero, and the insecure-cookie bug
this whole setting exists to prevent would come back — with no error. So
`pyproject.toml` now requires `uvicorn[standard]>=0.31.0`, with the reason in a
comment next to it.

## How this is kept from rotting

Two tests, both in `tests/test_ui.py`:

- `test_forwarded_proto_is_trusted_from_a_containerized_proxy` drives uvicorn's
  real `ProxyHeadersMiddleware` and asserts three directions: loopback-only
  trust → insecure cookie, the shipped default with a proxy at `10.0.1.5` →
  secure cookie, the shipped default with a public client at `203.0.113.7` →
  insecure cookie. The third assertion is the one that fails if someone
  reintroduces `*`.
- `test_forwarded_allow_ips_default_covers_container_networks` parses every
  entry through uvicorn's own `_TrustedHosts` and fails if any lands in
  `trusted_literals`. That is the silent failure mode: uvicorn does not reject a
  malformed entry, it falls back to literal string matching, which can never
  match a real client address. A typo would narrow trust to nothing with no
  symptom, and this test is what would say so.

`tests/test_version_sync.py::test_uvicorn_is_configured_to_trust_the_proxy`
continues to assert the `uvicorn.run()` kwargs stay wired, since nothing else
exercises them.
