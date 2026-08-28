"""Parse Hermes decompose JSON into HandoffResponse items."""

from __future__ import annotations

import json
import re
from typing import Any

from .config import load_config

VALID_COLUMNS = frozenset({"you", "agent", "waiting"})


class DecomposeError(Exception):
    pass


def _extract_json_blob(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            loaded = json.loads(fence.group(1).strip())
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            loaded = json.loads(text[start : end + 1])
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            return None
    return None


def parse_decompose_json(
    raw: str,
    run_id: str,
    handoff: dict[str, Any],
) -> dict[str, Any] | None:
    blob = _extract_json_blob(raw)
    if not blob or not isinstance(blob.get("items"), list):
        return None

    url = str(handoff.get("url") or "")
    human_tab_id = handoff.get("human_tab_id")
    agent_tab_id = handoff.get("agent_tab_id")
    title_max = load_config().prompts.work_item_title_max_chars
    items_out: list[dict[str, Any]] = []
    col_counts: dict[str, int] = {}

    for raw_item in blob["items"]:
        if not isinstance(raw_item, dict):
            continue
        column = str(raw_item.get("column", "")).lower()
        if column not in VALID_COLUMNS:
            continue
        idx = col_counts.get(column, 0)
        col_counts[column] = idx + 1
        item_id = f"{run_id}_{column}_{idx}"
        item: dict[str, Any] = {
            "id": item_id,
            "column": column,
            "title": str(raw_item.get("title") or "Untitled").strip()[:title_max],
            "source": {"kind": "handoff", "url": url},
            "status": raw_item.get("status") or "proposed",
            "run_id": run_id,
        }
        if human_tab_id is not None:
            item["human_tab_id"] = human_tab_id
        if column != "agent" and agent_tab_id is not None:
            item["agent_tab_id"] = agent_tab_id
        proposals = raw_item.get("proposals")
        if isinstance(proposals, list) and proposals:
            norm_props = []
            for pi, prop in enumerate(proposals):
                if not isinstance(prop, dict):
                    continue
                norm_props.append(
                    {
                        "id": prop.get("id") or f"{item_id}_prop_{pi}",
                        "kind": prop.get("kind") or "other",
                        "payload": prop.get("payload") or {},
                        "requires": prop.get("requires") or "accept",
                    }
                )
            item["proposals"] = norm_props
        else:
            item["proposals"] = []
        items_out.append(item)

    if not items_out:
        return None

    max_items = load_config().prompts.decompose_items_max
    if len(items_out) > max_items:
        items_out = items_out[:max_items]

    decomposition = str(blob.get("decomposition") or "").strip()
    return {
        "run_id": run_id,
        "decomposition": decomposition or "Handoff decomposed into board items.",
        "items": items_out,
    }
