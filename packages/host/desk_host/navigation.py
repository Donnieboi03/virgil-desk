"""Navigation op selection — mirrors extension tabPolicy.js."""

from __future__ import annotations


def choose_navigation_op(handoff_url: str, target_url: str) -> str:
    """Always openTab — extension uses create({ active: false }), never tabs.duplicate."""
    del handoff_url, target_url
    return "openTab"


def normalize_browser_command(command: dict) -> dict:
    """Map navigate / duplicateTab + url to openTab.

    Promote params.url → top-level url when CLI/Hermes put the destination
    only in --params (common misuse that otherwise opens about:blank).
    """
    out = dict(command)
    params = out.get("params")
    if isinstance(params, dict):
        nested = params.get("url")
        if nested and not out.get("url"):
            out["url"] = nested
    op = out.get("op", "")
    if op in {"navigate", "duplicateTab"}:
        out["op"] = "openTab"
    return out
