"""CLI: desk events --run-id …"""

from __future__ import annotations

import argparse
import json
from typing import Any

from .observability import read_events


def _field(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Read from measure/flags first, then legacy top-level."""
    for key in keys:
        for section in ("measure", "flags"):
            block = row.get(section)
            if isinstance(block, dict) and key in block:
                return block[key]
        if key in row:
            return row[key]
    return default


def _summarize_run(rows: list[dict[str, Any]]) -> dict[str, Any]:
    screenshot_count = 0
    live: bool | None = None
    item_count: int | None = None
    kinds: dict[str, int] = {}
    limits: dict[str, Any] | None = None
    failed_ops: list[dict[str, Any]] = []
    for row in rows:
        k = str(row.get("kind") or "")
        kinds[k] = kinds.get(k, 0) + 1
        if k == "browser.command_result":
            if _field(row, "has_screenshot"):
                screenshot_count += 1
            else:
                screenshot_count += int(row.get("screenshot_count") or 0)
            ok = _field(row, "ok")
            if ok is False:
                failed_ops.append(
                    {
                        "op": row.get("op"),
                        "error": row.get("error"),
                        "tab_id": row.get("tab_id"),
                        "url": row.get("url"),
                        "command_id": row.get("command_id"),
                    }
                )
        if k == "handoff.decomposed":
            if _field(row, "live") is not None:
                live = bool(_field(row, "live"))
            ic = _field(row, "item_count")
            if ic is not None:
                item_count = int(ic)
        if limits is None and isinstance(row.get("limits"), dict):
            limits = row["limits"]
    out: dict[str, Any] = {
        "event_count": len(rows),
        "kinds": kinds,
        "screenshot_count": screenshot_count,
        "live_decompose": live,
        "failed_command_count": len(failed_ops),
    }
    if failed_ops:
        out["failed_ops"] = failed_ops[:20]
    if item_count is not None:
        out["item_count"] = item_count
    if limits is not None:
        out["limits"] = limits
    return out


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
