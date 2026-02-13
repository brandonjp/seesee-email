"""SMTP ingest server using aiosmtpd.

Listens on a configurable port (default 2525) and:
1. Authenticates senders against per-app SMTP credentials
2. Parses MIME messages (extracts to, from, subject, HTML/text body)
3. Logs the email to the database
4. Optionally relays the message to an upstream SMTP server
"""

# TODO: Implement SMTP handler
# TODO: Implement SMTP AUTH with per-app credentials
# TODO: Implement MIME message parsing
# TODO: Implement optional upstream relay
