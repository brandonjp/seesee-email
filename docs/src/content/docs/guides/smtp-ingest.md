---
title: SMTP Ingest
description: Capture emails by pointing your app's SMTP settings at SeeSee.
---

SeeSee includes a built-in SMTP server powered by `aiosmtpd`. Instead of integrating the REST API, you can point your application's SMTP settings at SeeSee and it will capture every outgoing email automatically.

## How it works

1. Your app sends email via SMTP to SeeSee (default port 2525)
2. SeeSee authenticates the connection using per-app SMTP credentials
3. The MIME message is parsed — subject, addresses, HTML body, text body are extracted
4. The email is stored in the database, respecting the app's body storage mode
5. **Optionally**, SeeSee relays the message to an upstream SMTP server for actual delivery

```
Your App → SMTP (port 2525) → SeeSee → Database
                                  ↓
                            Optional Relay → Real SMTP Server → Delivery
```

## Setup

### 1. Enable SMTP

SMTP is enabled by default. Verify with:

```bash
SEESEE_SMTP_ENABLED=true   # default
SEESEE_SMTP_PORT=2525       # default
```

Make sure port 2525 is exposed in your Docker setup:

```bash
docker run -p 8080:8080 -p 2525:2525 ...
```

### 2. Create an app

Each app gets unique SMTP credentials on creation:

```bash
curl -X POST http://localhost:8080/api/v1/apps \
  -u admin:your-password \
  -H "Content-Type: application/json" \
  -d '{"name": "My App"}'
```

Save the `smtp_username` and `smtp_password` from the response — they're shown once.

### 3. Configure your app's SMTP settings

Point your application at SeeSee:

| Setting | Value |
|---------|-------|
| **SMTP Host** | Your SeeSee server IP or hostname |
| **SMTP Port** | `2525` |
| **Username** | `smtp_username` from app creation |
| **Password** | `smtp_password` from app creation |
| **Encryption** | None (for internal/local use) |
| **Auth** | Required (LOGIN or PLAIN) |

## Client configuration examples

### Generic SMTP settings

```
Host:     seesee.example.com
Port:     2525
Username: my-app
Password: (smtp password from app creation)
Auth:     LOGIN or PLAIN
TLS:      None (use a reverse proxy for TLS)
```

### Python (smtplib)

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

### PHP (mail function with SMTP)

Using PHPMailer (most common PHP SMTP library):

```php
use PHPMailer\PHPMailer\PHPMailer;

$mail = new PHPMailer(true);
$mail->isSMTP();
$mail->Host       = 'seesee.example.com';
$mail->SMTPAuth   = true;
$mail->Username   = 'my-app';
$mail->Password   = 'smtp-password-here';
$mail->Port       = 2525;
$mail->SMTPSecure = false;
$mail->SMTPAutoTLS = false;

$mail->setFrom('app@example.com', 'My App');
$mail->addAddress('user@example.com');
$mail->Subject = 'Test Email';
$mail->Body    = '<h1>Hello!</h1>';
$mail->AltBody = 'Hello!';

$mail->send();
```

### Node.js (Nodemailer)

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

## Relay configuration

By default, SeeSee only **captures** SMTP messages — it doesn't deliver them. To also deliver emails, configure an upstream relay:

```bash
SEESEE_SMTP_RELAY_HOST=smtp.gmail.com
SEESEE_SMTP_RELAY_PORT=587
SEESEE_SMTP_RELAY_USERNAME=your-email@gmail.com
SEESEE_SMTP_RELAY_PASSWORD=your-app-password
SEESEE_SMTP_RELAY_TLS=true
```

With relay enabled, SeeSee will:

1. Parse and store the email (as always)
2. Forward the original raw message to the upstream server
3. Log relay success or failure in the email's `error_message` field

This lets you use SeeSee as a transparent logging proxy — your emails still get delivered, and you have a complete log.

### Relay providers

Any standard SMTP server works as a relay target:

| Provider | Host | Port | TLS |
|----------|------|------|-----|
| Gmail | `smtp.gmail.com` | `587` | yes |
| Amazon SES | `email-smtp.us-east-1.amazonaws.com` | `587` | yes |
| SendGrid | `smtp.sendgrid.net` | `587` | yes |
| Mailgun | `smtp.mailgun.org` | `587` | yes |
| Postmark | `smtp.postmarkapp.com` | `587` | yes |
| Custom | Your SMTP server | Varies | Varies |

## Troubleshooting

### Connection refused

- Verify port 2525 is exposed: `docker run -p 2525:2525 ...`
- Check that `SEESEE_SMTP_ENABLED=true`
- If connecting from another container, use the host IP or Docker network name, not `localhost`
- Check firewall rules allow connections on port 2525

### Authentication failed

- SMTP credentials are per-app — make sure you're using the right app's credentials
- Credentials are shown only once at app creation. If lost, create a new app
- SeeSee supports LOGIN and PLAIN auth mechanisms

### Emails not appearing

- Check SeeSee logs for parsing errors: `docker logs seesee`
- Verify the SMTP user/password match a registered app
- Check the app's `body_storage_mode` — in `preview` mode, bodies are truncated to 500 characters

### Relay failures

- Check relay credentials and host/port
- Verify the relay server accepts connections from your SeeSee server's IP
- Relay errors are logged in the email's `error_message` field — check via API or Web UI
- Set `SEESEE_LOG_LEVEL=debug` for detailed SMTP relay logs
