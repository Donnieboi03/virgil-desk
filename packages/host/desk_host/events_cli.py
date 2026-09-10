"""CLI: desk events --run-id …"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from typing import Any

from .observability import read_events

# Full-run summary must not silently truncate at the default read window.
_SUMMARY_READ_LIMIT = 100_000


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


def _parse_ts(row: dict[str, Any]) -> float | None:
    raw = row.get("ts")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _item_id(row: dict[str, Any]) -> str | None:
    iid = row.get("item_id")
    if iid is None:
        return None
    text = str(iid).strip()
    return text or None


def _duration_ms(row: dict[str, Any]) -> int:
    val = _field(row, "duration_ms", default=0)
    try:
        return max(0, int(val or 0))
    except (TypeError, ValueError):
        return 0


def _execute_item_timelines(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-item EXT/GAP from execute_started → executed/failed windows."""
    indexed = [(i, row, _parse_ts(row)) for i, row in enumerate(rows)]
    starts: list[tuple[int, dict[str, Any], float | None, str]] = []
    for i, row, ts in indexed:
        if row.get("kind") != "agent.execute_started":
            continue
        iid = _item_id(row)
        if not iid:
            continue
        starts.append((i, row, ts, iid))

    items: list[dict[str, Any]] = []
    for start_i, start_row, start_ts, iid in starts:
        end_i = None
        end_ts = None
        end_kind = None
        for j, row, ts in indexed:
            if j <= start_i:
                continue
            if row.get("kind") not in ("agent.executed", "agent.execute_failed"):
                continue
            if _item_id(row) != iid:
                continue
            end_i = j
            end_ts = ts
            end_kind = str(row.get("kind"))
            break
        if end_i is None:
            continue

        window = indexed[start_i : end_i + 1]
        results: list[tuple[float | None, dict[str, Any]]] = []
        commands: list[tuple[float | None, dict[str, Any]]] = []
        for _, row, ts in window:
            kind = row.get("kind")
            if kind == "browser.command_result":
                results.append((ts, row))
            elif kind == "browser.command":
                commands.append((ts, row))

        # Prefer item_id join when browser events carry it; else time-window (legacy JSONL).
        stamped = any(_item_id(row) == iid for _, row in results + commands)
        if stamped:
            results = [(ts, row) for ts, row in results if _item_id(row) == iid]
            commands = [(ts, row) for ts, row in commands if _item_id(row) == iid]

        ext_ms = 0
        op_ext: list[dict[str, Any]] = []
        for ts, row in results:
            dur = _duration_ms(row)
            ext_ms += dur
            op_ext.append(
                {
                    "op": row.get("op") or _field(row, "op"),
                    "duration_ms": dur,
                    "inject_ms": _field(row, "inject_ms"),
                    "frame_count": _field(row, "frame_count"),
                }
            )

        gaps: list[int] = []
        for idx, (ts, row) in enumerate(results):
            if ts is None:
                continue
            next_cmd_ts = None
            for cts, _crow in commands:
                if cts is not None and cts > ts:
                    next_cmd_ts = cts
                    break
            if next_cmd_ts is None and idx + 1 < len(results):
                next_ts, next_row = results[idx + 1]
                if next_ts is not None:
                    # Approximate next command time as result_ts - duration.
                    next_cmd_ts = next_ts - (_duration_ms(next_row) / 1000.0)
            if next_cmd_ts is None:
                continue
            gaps.append(max(0, int(round((next_cmd_ts - ts) * 1000))))

        wall_ms = 0
        if start_ts is not None and end_ts is not None:
            wall_ms = max(0, int(round((end_ts - start_ts) * 1000)))

        gap_ms_sum = sum(gaps)
        gap_first_ms = gaps[0] if gaps else None
        gap_later_avg = (
            int(round(sum(gaps[1:]) / len(gaps[1:]))) if len(gaps) > 1 else None
        )
        residual_ms = max(0, wall_ms - ext_ms - gap_ms_sum)

        usage = {}
        end_row = rows[end_i]
        measure = end_row.get("measure")
        if isinstance(measure, dict):
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "cost_usd",
            ):
                if measure.get(key) is not None:
                    usage[key] = measure[key]

        item: dict[str, Any] = {
            "item_id": iid,
            "end_kind": end_kind,
            "wall_ms": wall_ms,
            "ext_ms": ext_ms,
            "gap_ms_sum": gap_ms_sum,
            "residual_ms": residual_ms,
            "op_count": len(op_ext),
            "op_ext": op_ext,
        }
        if gap_first_ms is not None:
            item["gap_first_ms"] = gap_first_ms
        if gap_later_avg is not None:
            item["gap_later_avg"] = gap_later_avg
        if usage:
            item["usage"] = usage
        items.append(item)
    return items


def _summarize_run(rows: list[dict[str, Any]]) -> dict[str, Any]:
    screenshot_count = 0
    live: bool | None = None
    item_count: int | None = None
    kinds: dict[str, int] = {}
    limits: dict[str, Any] | None = None
    failed_ops: list[dict[str, Any]] = []
    usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
    }
    usage_seen = False
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
        measure = row.get("measure")
        if isinstance(measure, dict):
            for key in usage_totals:
                val = measure.get(key)
                if val is None:
                    continue
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    continue
                usage_totals[key] += num
                usage_seen = True
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
    if usage_seen:
        if usage_totals["prompt_tokens"]:
            out["prompt_tokens"] = int(usage_totals["prompt_tokens"])
        if usage_totals["completion_tokens"]:
            out["completion_tokens"] = int(usage_totals["completion_tokens"])
        if usage_totals["total_tokens"]:
            out["total_tokens"] = int(usage_totals["total_tokens"])
        if usage_totals["cost_usd"]:
            out["cost_usd"] = round(usage_totals["cost_usd"], 6)

    items = _execute_item_timelines(rows)
    if items:
        out["items"] = items
        ext_values = [it["ext_ms"] for it in items]
        out["ext_ms_max"] = max(ext_values)
        out["ext_ms_min"] = min(ext_values)
        if len(ext_values) >= 2:
            out["ext_ms_median"] = int(round(statistics.median(ext_values)))
        max_item = max(items, key=lambda it: it["ext_ms"])
        out["ext_ms_max_item_id"] = max_item["item_id"]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Virgil Desk events JSONL")
    parser.add_argument("--run-id", dest="run_id", default=None)
    parser.add_argument("--kind", dest="kind", default=None)
    parser.add_argument("--summary", action="store_true", help="Print run summary JSON")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    limit = args.limit
    if args.summary and args.run_id and args.limit == 100:
        limit = _SUMMARY_READ_LIMIT
    rows = read_events(run_id=args.run_id, kind=args.kind, limit=limit)
    if args.summary:
        print(json.dumps(_summarize_run(rows), indent=2))
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
