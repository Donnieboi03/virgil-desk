"""Append-only desk events JSONL."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def log_dir() -> Path:
    raw = os.environ.get("DESK_LOG_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".virgil-desk" / "logs"


def events_path() -> Path:
    return log_dir() / "desk_events.jsonl"


def emit(kind: str, run_id: str, fields: dict[str, Any] | None = None) -> None:
    path = events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "kind": kind,
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        **(fields or {}),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_events(*, run_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    path = events_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if run_id and row.get("run_id") != run_id:
                continue
            rows.append(row)
    return rows[-limit:]
