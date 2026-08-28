"""Policy: human tab ban, forbidden closing actions."""

from __future__ import annotations

import re

FORBIDDEN_PATTERNS = re.compile(
    r"\b(send|submit|pay|purchase|wire\s+funds|password\s+change)\b",
    re.I,
)

MUTATING_OPS = frozenset(
    {"click", "fill", "scroll", "scrape", "screenshot", "openTab", "duplicateTab"}
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
) -> str | None:
    if op != "captureHandoffSnapshot" and is_human_tab_target(op, tab_id, human_tab_id):
        return "human_tab_blocked"
    if FORBIDDEN_PATTERNS.search(text or ""):
        return "forbidden_action_token"
    return None


def requires_auto_verify(op: str) -> bool:
    return op in {"click", "fill"}
