"""Policy: human tab ban, forbidden closing actions."""

from __future__ import annotations

import re

FORBIDDEN_PATTERNS = re.compile(
    r"\b(send|submit|pay|purchase|wire\s+funds|password\s+change)\b",
    re.I,
)

MUTATING_OPS = frozenset(
    {"click", "fill", "upload", "scroll", "scrape", "screenshot", "openTab", "duplicateTab"}
)


def is_human_tab_target(op: str, tab_id: int | None, human_tab_id: int | None) -> bool:
    if human_tab_id is None or tab_id is None:
        return False
    if op == "captureHandoffSnapshot":
        return tab_id == human_tab_id
    return tab_id == human_tab_id and op in MUTATING_OPS


def policy_denied_reason(
    op: str,
    tab_id: int | None,
    human_tab_id: int | None,
    text: str = "",
    params: dict | None = None,
    url: str | None = None,
) -> str | None:
    if op != "captureHandoffSnapshot" and is_human_tab_target(op, tab_id, human_tab_id):
        return "human_tab_blocked"
    # URL-first park: agents must not open human remainder tabs.
    if op == "openTab":
        placement = None
        if isinstance(params, dict):
            placement = params.get("placement")
        if placement == "human":
            return "human_park_tab_denied"
        target = (url or "").strip()
        if isinstance(params, dict) and not target:
            target = str(params.get("url") or "").strip()
        if not target or target == "about:blank" or not target.startswith(
            ("http://", "https://")
        ):
            return "open_tab_url_required"
    if FORBIDDEN_PATTERNS.search(text or ""):
        return "forbidden_action_token"
    return None


def requires_auto_verify(op: str) -> bool:
    return op in {"click", "fill", "upload"}
