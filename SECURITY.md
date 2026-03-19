# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in SeeSee, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email **security@brandonjp.com** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You should receive a response within 48 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest  | Yes       |

## Security Considerations

SeeSee is designed to be deployed on private networks or behind authentication. Please review the [deployment guide](https://seesee.email/guides/docker-deployment/) for security best practices:

- Always set a strong `SEESEE_ADMIN_PASSWORD`
- Use a reverse proxy with TLS for production deployments
- Keep SeeSee behind your firewall — it is not designed to be internet-facing without a proxy
- API keys are bcrypt-hashed and never stored in plaintext
- Session cookies are signed, HttpOnly, and SameSite=Lax
