"""Retention management — scheduled cleanup of old emails.

Evaluates per-app and global retention rules:
- max_count: Keep at most N emails per app
- max_age_days: Delete emails older than N days
- max_storage_mb: Global storage cap (oldest-first deletion)

The most restrictive rule wins when multiple apply.
Deletion is oldest-first within each app.
"""

# TODO: Implement retention scheduler
# TODO: Implement per-app rule evaluation
# TODO: Implement cleanup logging
