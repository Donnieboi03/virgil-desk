"""Desk shared notepad + last-N execute summaries + semantic facts (pure merge/truncate)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def empty_memory() -> dict[str, Any]:
    return {"global_recent": [], "by_run_id": {}}


def empty_semantic() -> dict[str, Any]:
    return {"facts": []}


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


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upsert_fact(
    semantic: dict[str, Any],
    *,
    key: str,
    value: str,
    tags: list[str] | None = None,
    source: str = "host",
    max_facts: int = 20,
    max_key_chars: int = 64,
    max_value_chars: int = 200,
) -> dict[str, Any]:
    """Upsert a semantic fact by ``key``; enforce length and count caps."""
    k = str(key or "").strip()[: max(0, max_key_chars)]
    v = str(value or "").strip()[: max(0, max_value_chars)]
    if not k or not v:
        return {
            "facts": list((semantic or {}).get("facts") or []),
        }
    tag_list = [str(t).strip() for t in (tags or []) if str(t).strip()]
    facts = list((semantic or {}).get("facts") or [])
    now = _iso_now()
    found = False
    for i, fact in enumerate(facts):
        if not isinstance(fact, dict):
            continue
        if str(fact.get("key") or "") == k:
            facts[i] = {
                **fact,
                "key": k,
                "value": v,
                "tags": tag_list,
                "source": source or fact.get("source") or "host",
                "updated_at": now,
                "id": fact.get("id") or uuid.uuid4().hex,
            }
            found = True
            break
    if not found:
        facts.append(
            {
                "id": uuid.uuid4().hex,
                "key": k,
                "value": v,
                "tags": tag_list,
                "source": source or "host",
                "updated_at": now,
            }
        )
    if max_facts > 0 and len(facts) > max_facts:
        facts = sorted(
            facts,
            key=lambda f: str((f or {}).get("updated_at") or ""),
        )[-max_facts:]
    return {"facts": facts}


def delete_fact(semantic: dict[str, Any], *, key: str = "", fact_id: str = "") -> dict[str, Any]:
    """Delete a fact by ``key`` or ``id``."""
    facts = list((semantic or {}).get("facts") or [])
    k = str(key or "").strip()
    fid = str(fact_id or "").strip()
    if not k and not fid:
        return {"facts": facts}
    out = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        if k and str(fact.get("key") or "") == k:
            continue
        if fid and str(fact.get("id") or "") == fid:
            continue
        out.append(fact)
    return {"facts": out}


def apply_semantic_patch(
    semantic: dict[str, Any],
    ops: list[dict[str, Any]],
    *,
    max_facts: int = 20,
    max_key_chars: int = 64,
    max_value_chars: int = 200,
) -> dict[str, Any]:
    """Apply upsert_fact | delete_fact ops."""
    out = {"facts": list((semantic or {}).get("facts") or [])}
    for op in ops or []:
        kind = op.get("op")
        if kind == "upsert_fact":
            out = upsert_fact(
                out,
                key=str(op.get("key") or ""),
                value=str(op.get("value") or ""),
                tags=list(op.get("tags") or []) if isinstance(op.get("tags"), list) else None,
                source=str(op.get("source") or "host"),
                max_facts=max_facts,
                max_key_chars=max_key_chars,
                max_value_chars=max_value_chars,
            )
        elif kind == "delete_fact":
            out = delete_fact(
                out,
                key=str(op.get("key") or ""),
                fact_id=str(op.get("id") or op.get("fact_id") or ""),
            )
    return out


def format_semantic_for_execute(
    semantic: dict[str, Any],
    *,
    packet_max_facts: int = 10,
    max_key_chars: int = 64,
    max_value_chars: int = 200,
) -> list[dict[str, Any]]:
    """Newest-first capped fact list for the execute Packet."""
    facts = [f for f in ((semantic or {}).get("facts") or []) if isinstance(f, dict)]
    facts = sorted(facts, key=lambda f: str(f.get("updated_at") or ""), reverse=True)
    if packet_max_facts > 0:
        facts = facts[:packet_max_facts]
    out: list[dict[str, Any]] = []
    for fact in facts:
        out.append(
            {
                "key": str(fact.get("key") or "")[: max(0, max_key_chars)],
                "value": str(fact.get("value") or "")[: max(0, max_value_chars)],
                "tags": list(fact.get("tags") or []),
            }
        )
    return out


def format_for_execute(
    memory: dict[str, Any],
    run_id: str,
    *,
    decomposition: str = "",
    semantic: dict[str, Any] | None = None,
    packet_max_facts: int = 10,
    max_key_chars: int = 64,
    max_value_chars: int = 200,
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
        "semantic_facts": format_semantic_for_execute(
            semantic or empty_semantic(),
            packet_max_facts=packet_max_facts,
            max_key_chars=max_key_chars,
            max_value_chars=max_value_chars,
        ),
    }
