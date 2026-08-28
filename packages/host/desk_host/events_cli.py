"""CLI: desk events --run-id …"""

from __future__ import annotations

import argparse
import json
from typing import Any

from .observability import read_events


def _summarize_run(rows: list[dict[str, Any]]) -> dict[str, Any]:
    screenshot_count = 0
    live: bool | None = None
    kinds: dict[str, int] = {}
    for row in rows:
        k = str(row.get("kind") or "")
        kinds[k] = kinds.get(k, 0) + 1
        if k == "browser.command_result":
            screenshot_count += int(row.get("screenshot_count") or 0)
        if k == "handoff.decomposed" and row.get("live") is not None:
            live = bool(row.get("live"))
    return {
        "event_count": len(rows),
        "kinds": kinds,
        "screenshot_count": screenshot_count,
        "live_decompose": live,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Virgil Desk events JSONL")
    parser.add_argument("--run-id", dest="run_id", default=None)
    parser.add_argument("--kind", dest="kind", default=None)
    parser.add_argument("--summary", action="store_true", help="Print run summary JSON")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    rows = read_events(run_id=args.run_id, kind=args.kind, limit=args.limit)
    if args.summary:
        print(json.dumps(_summarize_run(rows), indent=2))
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
