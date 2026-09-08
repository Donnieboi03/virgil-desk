"""Detect Hermes execute summaries that report failure or blocked tools."""

from __future__ import annotations

import re
from typing import Any

EXECUTE_FAILURE_RE = re.compile(
    r"(?i)"
    r"(timeout\s*[—\-]\s*denying\s+command"
    r"|unable to proceed"
    r"|blocked due to"
    r"|policy restriction"
    r"|I have paused"
    r"|cannot (?:proceed|run|execute)"
    r"|was blocked"
    r"|^\s*partial\s*:)",
)

# Hermes prepends this when --max-turns is hit; not a task failure by itself.
_MAX_ITER_BANNER = re.compile(
    r"(?im)"
    r"^\s*(?:⚠️\s*)?Reached maximum iterations(?:\s*\(\d+\))?[^\n]*\n?"
    r"(?:Requesting summary[^\n]*\n?)?",
)

_OPEN_CHILD_STATUSES = frozenset({"proposed", "running"})


def strip_max_iter_banner(text: str) -> str:
    """Drop Hermes max-turns wrap-up banner; keep the real summary body."""
    if not text:
        return ""
    return _MAX_ITER_BANNER.sub("", text).strip()


def execute_summary_indicates_failure(text: str) -> bool:
    return bool(EXECUTE_FAILURE_RE.search(text or ""))


def open_agent_children(
    parent_id: str, work_items: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Agent-column children still open under parent_id."""
    out: list[dict[str, Any]] = []
    for item in work_items.values():
        if item.get("parent_id") != parent_id:
            continue
        if item.get("column") != "agent":
            continue
        if item.get("status") not in _OPEN_CHILD_STATUSES:
            continue
        out.append(item)
    return out


def parent_done_blocked_reason(
    item: dict[str, Any], work_items: dict[str, dict[str, Any]]
) -> str | None:
    """
    Block parent done while agent children are proposed/running.
    Subtasks (parent_id set or kind=subtask) are never blocked by this gate.
    """
    if item.get("parent_id") or item.get("kind") == "subtask":
        return None
    kids = open_agent_children(str(item.get("id") or ""), work_items)
    if not kids:
        return None
    titles = ", ".join(str(k.get("title") or k.get("id")) for k in kids[:5])
    more = f" (+{len(kids) - 5} more)" if len(kids) > 5 else ""
    return f"open agent children remain: {titles}{more}"
