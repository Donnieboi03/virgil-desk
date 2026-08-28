"""CLI: desk events --run-id …"""

from __future__ import annotations

import argparse
import json

from .observability import read_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Virgil Desk events JSONL")
    parser.add_argument("--run-id", dest="run_id", default=None)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    rows = read_events(run_id=args.run_id, limit=args.limit)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
