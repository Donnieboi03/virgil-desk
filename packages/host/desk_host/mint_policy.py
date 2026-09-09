"""URL helpers for mint (no host-side remint dedupe — Resume uses Packet state)."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def normalize_resource_url(url: str | None) -> str | None:
    """
    Normalize URL: scheme/host/path/query, drop fragment,
    lowercase host, strip trailing slash on path (except root).
    """
    if not url or not str(url).strip():
        return None
    raw = str(url).strip()
    try:
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return raw.rstrip("/")
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                "",
                parsed.query,
                "",  # drop fragment
            )
        )
    except Exception:
        return raw.rstrip("/")
