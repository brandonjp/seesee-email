---
title: Integrations
description: Connect your apps to SeeSee with PHP, Python, Node.js, WordPress, and cURL.
---

SeeSee supports two ingest methods: **REST API** and **SMTP**. Each app you create gets both an API key (for REST) and SMTP credentials.

For REST API integration, your app sends a POST request to `/api/v1/log` after sending email. For SMTP integration, you point your app's SMTP settings at SeeSee and it captures messages automatically.

## cURL

The simplest way to test — log an email with a single command:

```bash
SEESEE_URL="https://seesee.example.com"
SEESEE_KEY="ss_your_api_key_here"

curl -X POST "${SEESEE_URL}/api/v1/log" \
  -H "Authorization: Bearer ${SEESEE_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["user@example.com"],
    "from": "app@example.com",
    "subject": "Test email from SeeSee",
    "body_text": "Hello from SeeSee!",
    "status": "sent",
    "provider": "smtp"
  }'
```

## Python

### REST API

```python
import httpx

SEESEE_URL = "https://seesee.example.com"
SEESEE_KEY = "ss_your_api_key_here"


def log_email(
    to: str | list[str],
    subject: str,
    body_text: str,
    *,
    from_addr: str = "noreply@example.com",
    provider: str = "resend",
    status: str = "sent",
    **kwargs,
) -> None:
    """Log a sent email to SeeSee."""
    httpx.post(
        f"{SEESEE_URL}/api/v1/log",
        headers={"Authorization": f"Bearer {SEESEE_KEY}"},
        json={
            "to": to if isinstance(to, list) else [to],
            "from": from_addr,
            "subject": subject,
            "body_text": body_text,
            "status": status,
            "provider": provider,
            **kwargs,
        },
        timeout=5,
    )


# Usage:
log_email("user@example.com", "Welcome!", "Thanks for signing up.")
```

Works with `httpx` or `requests` — swap `httpx.post` for `requests.post` with the same arguments.

### SMTP

```python
import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Hello from Python!")
msg["Subject"] = "Test Email"
msg["From"] = "app@example.com"
msg["To"] = "user@example.com"

with smtplib.SMTP("seesee.example.com", 2525) as server:
    server.login("my-app", "smtp-password-here")
    server.send_message(msg)
```

## JavaScript / Node.js

### REST API

```javascript
const SEESEE_URL = "https://seesee.example.com";
const SEESEE_KEY = "ss_your_api_key_here";

async function logEmail({
  to,
  from,
  subject,
  bodyHtml,
  bodyText,
  provider = "sendgrid",
  status = "sent",
  ...extra
}) {
  await fetch(`${SEESEE_URL}/api/v1/log`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${SEESEE_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      to: Array.isArray(to) ? to : [to],
      from,
      subject,
      body_html: bodyHtml,
      body_text: bodyText,
      status,
      provider,
      ...extra,
    }),
  });
}

// Usage:
await logEmail({
  to: "user@example.com",
  from: "noreply@myapp.com",
  subject: "Welcome!",
  bodyText: "Thanks for signing up.",
  provider: "resend",
});
```

### SMTP (Nodemailer)

```javascript
const nodemailer = require("nodemailer");

const transporter = nodemailer.createTransport({
  host: "seesee.example.com",
  port: 2525,
  secure: false,
  auth: {
    user: "my-app",
    pass: "smtp-password-here",
  },
});

await transporter.sendMail({
  from: "app@example.com",
  to: "user@example.com",
  subject: "Test Email",
  text: "Hello from Node.js!",
  html: "<h1>Hello from Node.js!</h1>",
});
```

## PHP / WordPress

### WordPress (wp_mail hook)

Drop this into your theme's `functions.php` or create a must-use plugin at `wp-content/mu-plugins/seesee.php`.

Define your credentials in `wp-config.php`:

```php
define('SEESEE_URL', 'https://seesee.example.com');
define('SEESEE_API_KEY', 'ss_your_api_key_here');
```

Then add the hooks:

```php
<?php
/**
 * SeeSee — WordPress Email Logging Hook
 * Automatically logs every email sent by wp_mail().
 */

add_action('wp_mail_succeeded', function ($mail_data) {
    if (! defined('SEESEE_URL') || ! defined('SEESEE_API_KEY')) {
        return;
    }

    wp_remote_post(SEESEE_URL . '/api/v1/log', [
        'headers' => [
            'Authorization' => 'Bearer ' . SEESEE_API_KEY,
            'Content-Type'  => 'application/json',
        ],
        'body' => json_encode([
            'to'        => (array) $mail_data['to'],
            'from'      => $mail_data['headers']['From'] ?? get_option('admin_email'),
            'subject'   => $mail_data['subject'],
            'body_html' => $mail_data['message'],
            'body_text' => wp_strip_all_tags($mail_data['message']),
            'status'    => 'sent',
            'provider'  => 'wp_mail',
        ]),
        'blocking' => false,  // Non-blocking — doesn't slow down wp_mail()
    ]);
});

add_action('wp_mail_failed', function ($error) {
    if (! defined('SEESEE_URL') || ! defined('SEESEE_API_KEY')) {
        return;
    }

    wp_remote_post(SEESEE_URL . '/api/v1/log', [
        'headers' => [
            'Authorization' => 'Bearer ' . SEESEE_API_KEY,
            'Content-Type'  => 'application/json',
        ],
        'body' => json_encode([
            'to'            => [],
            'from'          => get_option('admin_email'),
            'subject'       => 'Unknown',
            'status'        => 'failed',
            'error_message' => $error->get_error_message(),
            'provider'      => 'wp_mail',
        ]),
        'blocking' => false,
    ]);
});
```

This logs both successful sends and failures. The `blocking => false` option ensures logging doesn't slow down your WordPress site.

### WordPress (SMTP approach)

Instead of the REST API hook, you can use a WordPress SMTP plugin (e.g., WP Mail SMTP) and point it at SeeSee:

| Setting | Value |
|---------|-------|
| SMTP Host | `seesee.example.com` |
| SMTP Port | `2525` |
| Username | SMTP username from app creation |
| Password | SMTP password from app creation |
| Encryption | None |

SeeSee captures a copy of every email sent via SMTP. Your app should also send the email through its normal provider for actual delivery.

### PHP (standalone)

```php
<?php
$seesee_url = 'https://seesee.example.com';
$seesee_key = 'ss_your_api_key_here';

$payload = json_encode([
    'to'        => ['user@example.com'],
    'from'      => 'app@example.com',
    'subject'   => 'Test Email',
    'body_text' => 'Hello from PHP!',
    'status'    => 'sent',
    'provider'  => 'php',
]);

$ch = curl_init("{$seesee_url}/api/v1/log");
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => $payload,
    CURLOPT_HTTPHEADER     => [
        "Authorization: Bearer {$seesee_key}",
        'Content-Type: application/json',
    ],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 5,
]);
curl_exec($ch);
curl_close($ch);
```

## Best practices

- **Log after sending** — call SeeSee after your email provider confirms the send, so you can record the actual status
- **Use non-blocking calls** where possible (like WordPress's `blocking => false`) to avoid slowing down your app
- **Include provider info** — setting the `provider` field helps you filter by sending service in the dashboard
- **Log failures too** — recording failed sends with `error_message` helps debug delivery issues
- **Use tags** — the `tags` field lets you categorize emails (e.g., `["transactional", "signup"]`)
