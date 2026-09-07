#!/usr/bin/env python3
"""Tally Desk event metrics for one run_id (cross-branch Path compare helper).

Usage:
  python scripts/path_compare_metrics.py --run-id desk_abc
  python scripts/path_compare_metrics.py --run-id desk_abc --events ~/.virgil-desk/logs/desk_events.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Summarize desk_events for a run_id")
    p.add_argument("--run-id", required=True)
    p.add_argument(
        "--events",
        default=str(Path.home() / ".virgil-desk" / "logs" / "desk_events.jsonl"),
    )
    args = p.parse_args()
    path = Path(args.events).expanduser()
    if not path.is_file():
        print(f"events file not found: {path}")
        return 1

    kinds: Counter[str] = Counter()
    scrape_bytes: list[int] = []
    target_counts: list[int] = []
    drivers: Counter[str] = Counter()
    act_used: Counter[str] = Counter()
    duration_ms: list[int] = []

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(ev.get("run_id") or "") != args.run_id:
                continue
            kind = str(ev.get("kind") or ev.get("event") or "")
            kinds[kind] += 1
            measure = ev.get("measure") or {}
            if isinstance(measure, dict):
                if "scrape_bytes" in measure:
                    scrape_bytes.append(int(measure["scrape_bytes"]))
                if "target_count" in measure:
                    target_counts.append(int(measure["target_count"]))
                if "duration_ms" in measure:
                    duration_ms.append(int(measure["duration_ms"]))
            driver = ev.get("driver") or (ev.get("fields") or {}).get("driver")
            if driver:
                drivers[str(driver)] += 1
            ar = ev.get("act_resolved") or (ev.get("fields") or {}).get("act_resolved")
            if isinstance(ar, dict) and ar.get("used"):
                act_used[str(ar["used"])] += 1

    print(f"run_id={args.run_id}")
    print(f"events_file={path}")
    print(f"kinds={dict(kinds)}")
    print(f"drivers={dict(drivers)}")
    print(f"act_resolved.used={dict(act_used)}")
    if scrape_bytes:
        print(
            f"scrape_bytes: n={len(scrape_bytes)} max={max(scrape_bytes)} "
            f"avg={sum(scrape_bytes) // len(scrape_bytes)} ~tokens_max={max(scrape_bytes) // 4}"
        )
    if target_counts:
        print(
            f"target_count: n={len(target_counts)} max={max(target_counts)} "
            f"avg={sum(target_counts) / len(target_counts):.1f}"
        )
    if duration_ms:
        print(
            f"duration_ms: n={len(duration_ms)} max={max(duration_ms)} "
            f"sum={sum(duration_ms)}"
        )
    if not kinds:
        print("no events for this run_id — check path / DESK logging")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
