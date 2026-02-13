"""Shared helpers for email body processing.

Used by both the REST API ingest and SMTP ingest paths.
"""

import re


def apply_body_storage_mode(
    body_html: str | None,
    body_text: str | None,
    mode: str,
) -> tuple[str | None, str | None, str | None, int]:
    """Apply body storage mode and return (body_html, body_text, body_preview, body_size_bytes).

    body_size_bytes is calculated from the original body before any stripping.
    body_preview is always populated (first 500 chars of text content).
    """
    # Calculate original size before stripping
    body_size_bytes = 0
    if body_html:
        body_size_bytes += len(body_html.encode("utf-8"))
    if body_text:
        body_size_bytes += len(body_text.encode("utf-8"))

    # Generate preview: prefer body_text, fall back to stripped HTML
    preview_source = body_text
    if not preview_source and body_html:
        preview_source = strip_html_tags(body_html)

    body_preview = (preview_source or "")[:500] or None

    if mode == "text_only":
        return None, body_text, body_preview, body_size_bytes
    elif mode == "preview":
        return None, None, body_preview, body_size_bytes
    else:  # "full" or default
        return body_html, body_text, body_preview, body_size_bytes


def strip_html_tags(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()
