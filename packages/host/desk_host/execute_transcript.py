"""Host-owned execute transcript: Packet + Eyes trail + prune."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .prompt_render import render_prompt
from .thin_browser_result import thin_browser_response


def build_system_and_packet(item: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Initial messages: execute prompt system + Packet JSON (never pruned)."""
    system = render_prompt("execute_agent_item.md")
    packet = {"item": item, **ctx}
    # Host loop tools replace desk-browser CLI — steer the model briefly.
    system = (
        system
        + "\n\n## Host execute runtime\n\n"
        + "You are running under Host-owned tool calling (not a shell CLI). "
        + "Call the provided tools (`observe`, `click`, `fill`, `openTab`, "
        + "`duplicateTab`, `mint_item`, `probe_links`, …) with JSON arguments. "
        + "Do not invent shell commands. Prefer `target_id` from the latest observe.\n"
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "## Task\n\n```json\n"
            + json.dumps(packet, indent=2, default=str)
            + "\n```",
        },
    ]


def build_run_tab_messages(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Multi-item Run-tab Packet (system + one user JSON)."""
    system = render_prompt("execute_run_tab.md")
    # Avoid leaking mutable run_state object into the prompt JSON.
    packet = {
        k: v
        for k, v in ctx.items()
        if k not in ("run_state",)
    }
    system = (
        system
        + "\n\n## Host execute runtime\n\n"
        + "Host-owned tool calling. Use browser tools plus `complete_item` when each "
        + "Agent root is finished (done summary or Partial). Prefer `target_id`.\n"
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "## Run tab\n\n```json\n"
            + json.dumps(packet, indent=2, default=str)
            + "\n```",
        },
    ]


def _tool_payload_for_prune(content: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(content)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def stub_eyes_tool_content(payload: dict[str, Any]) -> str:
    """Compact stub replacing a full thinned Eyes tool result."""
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    op = result.get("op") or payload.get("op")
    stub = {
        "ok": result.get("ok", payload.get("ok")),
        "op": op,
        "url": result.get("url"),
        "stub": True,
        "note": "eyes_pruned",
    }
    if result.get("error"):
        stub["error"] = result.get("error")
    return json.dumps(stub, ensure_ascii=False)


# Eyes/Hands browser tools — mint_item and other non-Eyes payloads stay full.
_EYES_PRUNE_TOOL_NAMES = frozenset(
    {
        "observe",
        "click",
        "fill",
        "openTab",
        "duplicateTab",
        "probe_links",
        "probe_form",
        "probe_table",
        "press_key",
        "scroll",
        "closeTab",
        "scrape",
        "screenshot",
        "key",
        "wait",
    }
)


def prune_messages(
    messages: list[dict[str, Any]],
    *,
    eyes_keep_last: int,
) -> list[dict[str, Any]]:
    """
    Keep system/user/assistant intact. For tool-role messages with Eyes payloads,
    keep the last ``eyes_keep_last`` full; stub older ones.
    Never stubs ``mint_item`` (or other non-Eyes tools). Never touches the
    initial Packet user message or system message.
    """
    if eyes_keep_last < 0:
        eyes_keep_last = 0
    out = deepcopy(messages)
    tool_idxs = [
        i
        for i, m in enumerate(out)
        if m.get("role") == "tool"
        and isinstance(m.get("content"), str)
        and str(m.get("name") or "") in _EYES_PRUNE_TOOL_NAMES
    ]
    if len(tool_idxs) <= eyes_keep_last:
        return out
    drop = tool_idxs[:-eyes_keep_last] if eyes_keep_last > 0 else tool_idxs
    for i in drop:
        name = str(out[i].get("name") or "")
        if name not in _EYES_PRUNE_TOOL_NAMES:
            continue
        payload = _tool_payload_for_prune(str(out[i].get("content") or ""))
        if payload is None:
            continue
        # Already stubbed
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        if result.get("stub") is True or payload.get("stub") is True:
            continue
        op = str(result.get("op") or payload.get("op") or name)
        if op == "mint_item":
            continue
        out[i] = {
            **out[i],
            "content": stub_eyes_tool_content(payload),
        }
    return out


def append_assistant_tool_calls(
    messages: list[dict[str, Any]],
    *,
    content: str | None,
    tool_calls: list[dict[str, Any]],
) -> None:
    msg: dict[str, Any] = {"role": "assistant", "content": content or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    messages.append(msg)


def append_tool_result(
    messages: list[dict[str, Any]],
    *,
    tool_call_id: str,
    name: str,
    payload: dict[str, Any],
) -> None:
    thinned = thin_browser_response(payload) if isinstance(payload, dict) else payload
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": json.dumps(thinned, ensure_ascii=False),
        }
    )
