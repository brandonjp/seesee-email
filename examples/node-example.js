/**
 * SeeSee — Node.js integration example.
 *
 * Log sent emails to your SeeSee instance after sending via any provider.
 */

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
// await logEmail({
//   to: "user@example.com",
//   from: "noreply@myapp.com",
//   subject: "Welcome!",
//   bodyText: "Thanks for signing up.",
//   provider: "resend",
// });

module.exports = { logEmail };
