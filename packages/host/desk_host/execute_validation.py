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
    r"|reached maximum iterations?"
    r"|maximum iterations? reached"
    r"|^\s*partial\s*:)",
)


def execute_summary_indicates_failure(text: str) -> bool:
    return bool(EXECUTE_FAILURE_RE.search(text or ""))
