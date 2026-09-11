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
        "execute": asdict(c.execute),
        "memory": asdict(c.memory),
        "prompts": asdict(c.prompts),
    }


_USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
)


def usage_measure(usage: dict[str, Any] | None) -> dict[str, Any]:
    """Keep numeric usage/cost fields only; empty dict if nothing usable.

    Desk always *can* record these on measure; backends omit when absent.
    Never raise — callers merge into measure only when non-empty.
    """
    if not isinstance(usage, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _USAGE_KEYS:
        val = usage.get(key)
        if val is None:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if key.endswith("_tokens"):
            out[key] = int(num)
        else:
            out[key] = num
    return out


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
    scrape_tab = cap.get("used_scrape_tab")
    if scrape_tab is None:
        scrape_tab = cap.get("used_duplicate_tab")
    if scrape_tab is not None:
        flags["used_scrape_tab"] = bool(scrape_tab)
        flags["used_duplicate_tab"] = bool(scrape_tab)  # legacy alias
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


def site_fingerprint(url: str | None) -> str | None:
    """Stable-ish host+path prefix for procedure mining (not Eyes ladder mode)."""
    if not url or not isinstance(url, str):
        return None
    text = url.strip()
    if not text:
        return None
    try:
        from urllib.parse import urlparse

        parsed = urlparse(text)
    except Exception:
        return None
    host = (parsed.netloc or "").lower()
    if not host:
        return None
    path = parsed.path or "/"
    parts = [p for p in path.split("/") if p]
    first = parts[0] if parts else ""
    if first:
        return f"{host}/{first}"
    return host


def browser_command_result_fields(
    result: dict[str, Any],
    *,
    op: str | None = None,
    screenshot_count_run_total: int = 0,
) -> dict[str, Any]:
    """Shared measure/flags/detail for browser.command_result (extension + harness)."""
    resolved_op = op if op is not None else result.get("op")
    detail: dict[str, Any] = {
        "command_id": result.get("command_id"),
        "act_resolved": result.get("act_resolved"),
    }
    if resolved_op:
        detail["op"] = resolved_op
    if result.get("error") is not None:
        detail["error"] = result.get("error")
    if result.get("tab_id") is not None:
        detail["tab_id"] = result.get("tab_id")
    if result.get("url") is not None:
        detail["url"] = result.get("url")
    measure: dict[str, Any] = {
        "duration_ms": result.get("duration_ms"),
        "scrape_bytes": len(result.get("scrape_excerpt") or ""),
        "screenshot_count_run_total": screenshot_count_run_total,
        "target_count": len(result.get("interact_targets") or []),
    }
    if result.get("eyes_settle_ms") is not None:
        measure["eyes_settle_ms"] = result.get("eyes_settle_ms")
    if result.get("eyes_settle_attempts") is not None:
        measure["eyes_settle_attempts"] = result.get("eyes_settle_attempts")
    if result.get("inject_ms") is not None:
        measure["inject_ms"] = result.get("inject_ms")
    if result.get("frame_count") is not None:
        measure["frame_count"] = result.get("frame_count")
    flags: dict[str, Any] = {
        "ok": result.get("ok"),
        "has_screenshot": bool(result.get("screenshot")),
        "has_interact_targets": bool(result.get("interact_targets")),
    }
    if result.get("eyes_empty") is not None:
        flags["eyes_empty"] = bool(result.get("eyes_empty"))
    if result.get("eyes_mode") is not None:
        flags["eyes_mode"] = result.get("eyes_mode")
    if result.get("challenge_extended") is not None:
        flags["challenge_extended"] = bool(result.get("challenge_extended"))
    if result.get("eyes_hints") is not None:
        detail["eyes_hints"] = result.get("eyes_hints")
    return {
        "measure": measure,
        "flags": flags,
        "detail": detail,
    }


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
