"""Detect Hermes execute summaries that report failure or blocked tools."""

from __future__ import annotations

import re

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


def strip_max_iter_banner(text: str) -> str:
    """Drop Hermes max-turns wrap-up banner; keep the real summary body."""
    if not text:
        return ""
    return _MAX_ITER_BANNER.sub("", text).strip()


def execute_summary_indicates_failure(text: str) -> bool:
    return bool(EXECUTE_FAILURE_RE.search(text or ""))
