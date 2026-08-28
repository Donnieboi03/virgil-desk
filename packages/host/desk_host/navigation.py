"""Navigation op selection — mirrors extension tabPolicy.js."""

from __future__ import annotations

from urllib.parse import urlparse


def choose_navigation_op(handoff_url: str, target_url: str) -> str:
    if not target_url:
        return "openTab"
    try:
        h = urlparse(handoff_url)
        t = urlparse(target_url)
        if h.scheme and t.scheme and h.netloc == t.netloc and h.path == t.path:
            return "duplicateTab"
    except Exception:
        pass
    return "openTab"


def normalize_browser_command(command: dict) -> dict:
    """Map navigate + url to duplicateTab or openTab using handoff_url."""
    out = dict(command)
    op = out.get("op", "")
    url = out.get("url")
    handoff_url = out.get("handoff_url") or ""
    if op in {"navigate", "openTab", "duplicateTab"} and url and handoff_url:
        out["op"] = choose_navigation_op(handoff_url, url)
    elif op == "navigate" and url:
        out["op"] = "openTab"
    return out
