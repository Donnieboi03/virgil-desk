"""Append-only desk events JSONL + structured record envelope."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DeskConfig, load_config


def log_dir() -> Path:
    raw = os.environ.get("DESK_LOG_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".virgil-desk" / "logs"


def events_path() -> Path:
    return log_dir() / "desk_events.jsonl"


def limits_from_config(cfg: DeskConfig | None = None) -> dict[str, Any]:
    """Config limits in effect at event time — factual, not a root-cause claim."""
    c = cfg or load_config()
    return {
        "browser": asdict(c.browser),
        "host": asdict(c.host),
        "hermes": asdict(c.hermes),
        "prompts": asdict(c.prompts),
    }


def measure_from_snapshot(snap: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extension snapshot → measure + flags (no host config inference)."""
    cap = dict(snap.get("capture") or {})
    excerpt = snap.get("excerpt") or ""
    links = snap.get("links") or []
    shot = snap.get("screenshot") or {}
    measure: dict[str, Any] = {
        "excerpt_chars": cap.get("excerpt_chars", len(excerpt)),
        "scrape_text_chars": cap.get("scrape_text_chars"),
        "full_text_chars": cap.get("full_text_chars"),
        "link_count": cap.get("link_count", len(links)),
        "full_link_count": cap.get("full_link_count"),
        "screenshot_bytes": len(shot.get("base64") or ""),
        "scroll_loops_executed": cap.get("scroll_loops_executed"),
        "scroll_loops_configured": cap.get("scroll_loops_configured"),
        "scroll_viewport_ratio": cap.get("scroll_viewport_ratio"),
    }
    measure = {k: v for k, v in measure.items() if v is not None}
    flags: dict[str, Any] = {
        "has_screenshot": bool(shot.get("base64")),
        "scrape_text_capped": cap.get("scrape_text_capped"),
        "handoff_excerpt_capped": cap.get("handoff_excerpt_capped"),
        "links_capped": cap.get("links_capped"),
    }
    flags = {k: v for k, v in flags.items() if v is not None}
    return measure, flags


def record(
    kind: str,
    run_id: str,
    *,
    measure: dict[str, Any] | None = None,
    flags: dict[str, Any] | None = None,
    cfg: DeskConfig | None = None,
    include_limits: bool = True,
    **detail: Any,
) -> None:
    """Emit one desk event with a consistent observability envelope.

    - **limits**: config in effect (when include_limits=True)
    - **measure**: numeric / size facts about this action
    - **flags**: boolean facts (e.g. capped, ok) — not interpreted as cause
    - **detail**: action-specific ids, errors, labels (…kwargs)
    """
    payload: dict[str, Any] = dict(detail)
    if include_limits:
        payload["limits"] = limits_from_config(cfg)
    if measure:
        payload["measure"] = measure
    if flags:
        payload["flags"] = flags
    emit(kind, run_id, payload)


def emit(kind: str, run_id: str, fields: dict[str, Any] | None = None) -> None:
    path = events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        **(fields or {}),
        "kind": kind,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_events(
    *,
    run_id: str | None = None,
    kind: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
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
            if kind and row.get("kind") != kind:
                continue
            rows.append(row)
    return rows[-limit:]
