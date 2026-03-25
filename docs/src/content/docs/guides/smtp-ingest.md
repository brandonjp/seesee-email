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

```
Your App → SMTP (port 2525) → SeeSee → Database
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

Save the `api_key` and `smtp_username` from the response — they're shown once. Your API key is also your SMTP password.

### 3. Configure your app's SMTP settings

Point your application at SeeSee:

| Setting | Value |
|---------|-------|
| **SMTP Host** | Your SeeSee server IP or hostname |
| **SMTP Port** | `2525` |
| **Username** | `smtp_username` from app creation |
| **Password** | Your API key |
| **Encryption** | None (for internal/local use) |
| **Auth** | Required (LOGIN or PLAIN) |

## Client configuration examples

### Generic SMTP settings

```
Host:     seesee.example.com
Port:     2525
Username: my-app
Password: (your API key)
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
    server.login("my-app", "ss_your_api_key_here")
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
$mail->Password   = 'ss_your_api_key_here';
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
    pass: "ss_your_api_key_here",
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

## Troubleshooting

### Connection refused

- Verify port 2525 is exposed: `docker run -p 2525:2525 ...`
- Check that `SEESEE_SMTP_ENABLED=true`
- If connecting from another container, use the host IP or Docker network name, not `localhost`
- Check firewall rules allow connections on port 2525

### Authentication failed

- SMTP uses your app's API key as the password — make sure you're using the right app's key
- The API key is shown only once at app creation. If lost, rotate the key from the app detail page
- SeeSee supports LOGIN and PLAIN auth mechanisms

### Emails not appearing

- Check SeeSee logs for parsing errors: `docker logs seesee`
- Verify the SMTP user/password match a registered app
- Check the app's `body_storage_mode` — in `preview` mode, bodies are truncated to 500 characters

