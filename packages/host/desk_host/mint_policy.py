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


def normalize_gate_url(url: str | None) -> str | None:
    """
    Destination key for auth/challenge You parks: origin + pathname only
    (drop query/fragment) so Cloudflare vs login funnel collapses.
    """
    if not url or not str(url).strip():
        return None
    raw = str(url).strip()
    try:
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return raw.split("?", 1)[0].rstrip("/") or raw
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return urlunparse(
            (parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", "")
        )
    except Exception:
        return raw.split("?", 1)[0].rstrip("/") or raw


def find_idempotent_mint(
    work_items: dict[str, dict[str, Any]],
    *,
    parent_id: str,
    column: str,
    source_url: str | None,
    title: str | None = None,
    gate_dedupe: bool = False,
) -> dict[str, Any] | None:
    """
    Return an existing child under parent with same column and source URL
    Open statuses only (proposed/running/awaiting_human).

    When gate_dedupe=True (You auth parks), match on origin+path only,
    including already-done auth/resume parks so Resume cannot remint the same destination.
    """
    norm_fn = normalize_gate_url if gate_dedupe else normalize_resource_url
    norm = norm_fn(source_url)
    title_key = (title or "").strip().lower()
    open_statuses = ("proposed", "running", "awaiting_human")
    for item in work_items.values():
        if item.get("parent_id") != parent_id:
            continue
        if item.get("column") != column:
            continue
        status = item.get("status")
        if gate_dedupe:
            if status not in open_statuses and status != "done":
                continue
            if status == "done" and item.get("park_kind") != "auth_gate" and not item.get(
                "resume"
            ):
                continue
        elif status not in open_statuses:
            continue
        item_url = norm_fn((item.get("source") or {}).get("url"))
        if norm and item_url and norm == item_url:
            return item
        if not norm and title_key and (item.get("title") or "").strip().lower() == title_key:
            return item
    return None
