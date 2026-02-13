#!/bin/bash
# SeeSee — cURL integration example.
# Log a sent email to your SeeSee instance.

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
