"""Desk shared notepad + last-N execute summaries (pure merge/truncate)."""

from __future__ import annotations

from typing import Any


def empty_memory() -> dict[str, Any]:
    return {"global_recent": [], "by_run_id": {}}


def append_recent(
    memory: dict[str, Any],
    entry: dict[str, Any],
    *,
    recent_max: int = 3,
) -> dict[str, Any]:
    """Append an execute summary; keep only the newest ``recent_max`` entries."""
    out = {
        "global_recent": list(memory.get("global_recent") or []),
        "by_run_id": dict(memory.get("by_run_id") or {}),
    }
    out["global_recent"].append(entry)
    if recent_max > 0 and len(out["global_recent"]) > recent_max:
        out["global_recent"] = out["global_recent"][-recent_max:]
    return out


def seed_run_notepad(
    memory: dict[str, Any],
    run_id: str,
    *,
    decomposition: str = "",
    mission: str = "",
) -> dict[str, Any]:
    out = {
        "global_recent": list(memory.get("global_recent") or []),
        "by_run_id": dict(memory.get("by_run_id") or {}),
    }
    existing = dict(out["by_run_id"].get(run_id) or {})
    out["by_run_id"][run_id] = {
        "decomposition": decomposition or existing.get("decomposition") or "",
        "mission": mission or existing.get("mission") or "",
        "bullets": list(existing.get("bullets") or []),
    }
    return out


def append_notepad_bullet(
    memory: dict[str, Any],
    run_id: str,
    bullet: str,
    *,
    max_bullets: int = 20,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Append one notepad bullet for ``run_id``; trim by count and total chars."""
    text = (bullet or "").strip()
    if not text:
        return {
            "global_recent": list(memory.get("global_recent") or []),
            "by_run_id": dict(memory.get("by_run_id") or {}),
        }
    out = seed_run_notepad(memory, run_id)
    note = out["by_run_id"][run_id]
    bullets = list(note.get("bullets") or [])
    bullets.append(text)
    if max_bullets > 0 and len(bullets) > max_bullets:
        bullets = bullets[-max_bullets:]
    while max_chars > 0 and bullets and sum(len(b) for b in bullets) > max_chars:
        bullets.pop(0)
    note["bullets"] = bullets
    return out


def apply_memory_patch(
    memory: dict[str, Any],
    ops: list[dict[str, Any]],
    *,
    recent_max: int = 3,
    max_bullets: int = 20,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Apply host→extension memory ops (seed_run | append_recent | append_bullet)."""
    out = {
        "global_recent": list(memory.get("global_recent") or []),
        "by_run_id": dict(memory.get("by_run_id") or {}),
    }
    for op in ops:
        kind = op.get("op")
        if kind == "seed_run":
            out = seed_run_notepad(
                out,
                str(op.get("run_id") or ""),
                decomposition=str(op.get("decomposition") or ""),
                mission=str(op.get("mission") or ""),
            )
        elif kind == "append_recent":
            entry = op.get("entry") or {}
            if isinstance(entry, dict) and entry:
                out = append_recent(out, entry, recent_max=recent_max)
        elif kind == "append_bullet":
            out = append_notepad_bullet(
                out,
                str(op.get("run_id") or ""),
                str(op.get("bullet") or ""),
                max_bullets=max_bullets,
                max_chars=max_chars,
            )
    return out


def format_for_execute(
    memory: dict[str, Any],
    run_id: str,
    *,
    decomposition: str = "",
) -> dict[str, Any]:
    """Slice memory fields injected into Hermes execute context."""
    note = (memory.get("by_run_id") or {}).get(run_id) or {}
    decomp = decomposition or note.get("decomposition") or ""
    return {
        "recent_executions": list(memory.get("global_recent") or []),
        "run_notepad": {
            "decomposition": decomp,
            "mission": note.get("mission") or "",
            "bullets": list(note.get("bullets") or []),
        },
        "decomposition": decomp,
    }
