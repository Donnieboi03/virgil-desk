"""Detect Hermes execute summaries that report failure or incomplete done claims."""

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

_OPEN_ONLY_SUMMARY_RE = re.compile(
    r"(?i)^\s*(observed|opened)\b",
)

# Verified terminal outcomes (review/check goals) count as Completed — not Partial/park.
_VERIFIED_TERMINAL_DONE_RE = re.compile(
    r"(?i)\b("
    r"verified\s+(?:expired|terminal|status|outcome|page|already\s+submitted)"
    r"|already\s+submitted"
    r"|deadline\s+(?:has\s+)?passed"
    r"|7[\s-]?day\s+deadline"
    r"|expired[\s-]?or[\s-]?not[\s-]?found"
    r"|link\s+(?:has\s+)?expired"
    r"|invitation\s+(?:has\s+)?expired"
    r"|no\s+longer\s+(?:available|valid)"
    r"|screening\s+(?:link\s+)?(?:expired|already\s+submitted)"
    r"|review\s+(?:complete|completed|done)\b"
    r"|completed\s+review\b"
    r")\b",
)

_EXPLICIT_DONE_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"single[\s-]?closure"
    r"|no further (?:closures|action|agent|human)"
    r"|remainder parked"
    r"|parked (?:for|with) (?:human|you)"
    r"|parked .{0,40}\bYou\b"
    r"|to You column"
    r"|human (?:review )?subtasks?"
    r"|minted\b"
    r")\b",
)

_OPEN_CHILD_STATUSES = frozenset({"proposed", "running"})


def strip_max_iter_banner(text: str) -> str:
    """Drop Hermes max-turns wrap-up banner; keep the real summary body."""
    if not text:
        return ""
    return _MAX_ITER_BANNER.sub("", text).strip()


def execute_summary_indicates_failure(text: str) -> bool:
    return bool(EXECUTE_FAILURE_RE.search(text or ""))


def execute_summary_claims_done(text: str) -> bool:
    """True when summary has park/mint/single-closure or verified-terminal language."""
    body = strip_max_iter_banner(text or "")
    if not body:
        return False
    return bool(
        _EXPLICIT_DONE_CLAIM_RE.search(body) or _VERIFIED_TERMINAL_DONE_RE.search(body)
    )


def execute_summary_incomplete_reason(text: str) -> str | None:
    """
    Host/Hermes gate: open-only “Observed/Opened …” is not done.
    Allow explicit single-closure / parked / verified-terminal claims.
    Partial: handled as failure elsewhere.
    """
    body = strip_max_iter_banner(text or "")
    if not body:
        return "empty execute summary"
    if execute_summary_indicates_failure(body):
        return None
    if execute_summary_claims_done(body):
        return None
    if _OPEN_ONLY_SUMMARY_RE.search(body):
        return (
            "open-only observation is not done — finish work, verify terminal "
            "page state, park remainder (mint_item You + source.url), "
            "claim single-closure, or Partial:"
        )
    return None


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


def failed_open_tab_blocks_done(
    *,
    failed_ops: list[str],
    summary: str,
) -> str | None:
    """
    Reject success summaries when openTab/duplicateTab failed mid-run
    (unless Partial / parked / single-closure / minted / verified-terminal).
    """
    if not any(op in ("openTab", "duplicateTab") for op in failed_ops):
        return None
    body = strip_max_iter_banner(summary or "")
    if not body:
        return None
    if execute_summary_indicates_failure(body):
        return None
    if execute_summary_claims_done(body):
        return None
    return (
        "openTab/duplicateTab failed mid-run — Partial:, park You (mint_item), or retry"
    )

def empty_probe_links_only_cover(
    *,
    ops_since_start: list[str],
    last_probe_links_empty: bool,
) -> str | None:
    """
    If execute used probe_links and it returned empty, that does not count as
    having checked in-body links — reject when that was the only post-open Eyes.
    """
    if not last_probe_links_empty:
        return None
    if "probe_links" not in ops_since_start:
        return None
    # Empty probe as last meaningful Eyes step after open/click → incomplete.
    meaningful = [op for op in ops_since_start if op not in ("scrape",)]
    if meaningful and meaningful[-1] == "probe_links":
        return (
            "empty probe_links is not link-check — re-observe, follow link targets, "
            "or Partial:"
        )
    return None


_FALSE_CLOSURE_RE = re.compile(
    r"(?i)\b(single[\s-]?closure|no further (?:closures|action|agent|human))\b"
)
_HONEST_REMAINDER_RE = re.compile(
    r"(?i)\b(awaiting|parked|remainder|you column|human (?:view|review|glance)|resume)\b"
)

# Titles that usually need the operator as source of closure (not agent-only read).
_HUMAN_JUDGMENT_TITLE_RE = re.compile(
    r"(?i)\b("
    r"review|respond|reply|decide|choose|pick|match|access|apply|consider|approve"
    r")\b"
)

# Summary language that looks like "I read it" sold as Done without a human park.
_READ_ONLY_FALSE_DONE_RE = re.compile(
    r"(?i)\b("
    r"reviewed\b"
    r"|verified\s+(?:access|profile|details|picks?)"
    r"|opened\s+shared\s+folder"
    r"|verified\s+access\s+to"
    r"|profile\s+details"
    r")\b"
)


def open_auth_gate_you(
    parent_id: str, work_items: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Open You child with park_kind=auth_gate (or resume) under parent."""
    for item in work_items.values():
        if item.get("parent_id") != parent_id:
            continue
        if item.get("column") != "you":
            continue
        if item.get("park_kind") != "auth_gate" and not item.get("resume"):
            continue
        if item.get("status") not in ("proposed", "running"):
            continue
        return item
    return None


def open_you_remainder(
    parent_id: str, work_items: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Open You child that still needs human (auth_gate or human_remainder)."""
    for item in work_items.values():
        if item.get("parent_id") != parent_id:
            continue
        if item.get("column") != "you":
            continue
        if item.get("status") not in ("proposed", "running"):
            continue
        kind = item.get("park_kind")
        if kind in ("auth_gate", "human_remainder") or item.get("resume"):
            return item
    return None


def auth_gate_blocks_false_closure(
    summary: str, *, has_auth_gate_you: bool
) -> str | None:
    """
    Reject single-closure / no-further-action when a You gate/remainder still needs human.
    """
    if not has_auth_gate_you:
        return None
    body = strip_max_iter_banner(summary or "")
    if not body:
        return None
    if execute_summary_indicates_failure(body):
        return None
    if _FALSE_CLOSURE_RE.search(body) and not _HONEST_REMAINDER_RE.search(body):
        return (
            "You park remains — do not claim single-closure/no further action; "
            "leave parent awaiting_human or acknowledge parked remainder"
        )
    return None


def human_judgment_blocks_false_closure(
    summary: str,
    *,
    item_title: str = "",
    has_you_remainder: bool = False,
) -> str | None:
    """
    Reject 'Single closure / no further action' after only reading when the human
    still must decide, reply, apply, or use docs (unless verified terminal or You park).
    """
    if has_you_remainder:
        return None
    body = strip_max_iter_banner(summary or "")
    if not body:
        return None
    if execute_summary_indicates_failure(body):
        return None
    if _VERIFIED_TERMINAL_DONE_RE.search(body):
        return None
    if _HONEST_REMAINDER_RE.search(body):
        return None
    if not _FALSE_CLOSURE_RE.search(body):
        return None
    title_needs_human = bool(_HUMAN_JUDGMENT_TITLE_RE.search(item_title or ""))
    read_sold_as_done = bool(_READ_ONLY_FALSE_DONE_RE.search(body))
    if title_needs_human or read_sold_as_done:
        return (
            "human judgment/use remains — mint human_remainder You with source.url "
            "for each decision or doc the operator must act on; do not claim "
            "single-closure/no further action after only reading"
        )
    return None
