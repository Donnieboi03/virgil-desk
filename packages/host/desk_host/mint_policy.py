"""Mint / park idempotency helpers (pure)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse


def normalize_resource_url(url: str | None) -> str | None:
    """
    Normalize URL for mint/park dedupe: scheme/host/path/query, drop fragment,
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


def find_idempotent_mint(
    work_items: dict[str, dict[str, Any]],
    *,
    parent_id: str,
    column: str,
    source_url: str | None,
    title: str | None = None,
) -> dict[str, Any] | None:
    """
    Return an existing child under parent with same column and source URL
    (or same title when no URL). Open statuses only (proposed/running).
    """
    norm = normalize_resource_url(source_url)
    title_key = (title or "").strip().lower()
    for item in work_items.values():
        if item.get("parent_id") != parent_id:
            continue
        if item.get("column") != column:
            continue
        if item.get("status") not in ("proposed", "running"):
            continue
        item_url = normalize_resource_url((item.get("source") or {}).get("url"))
        if norm and item_url and norm == item_url:
            return item
        if not norm and title_key and (item.get("title") or "").strip().lower() == title_key:
            return item
    return None
