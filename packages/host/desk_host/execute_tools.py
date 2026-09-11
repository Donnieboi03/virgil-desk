"""Host-loop tool schemas + dispatch into browser / mint (no Hermes CLI)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from .config import load_config


BROWSER_TOOL_NAMES = frozenset(
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
    }
)


def host_loop_tools(*, include_complete_item: bool = False) -> list[dict[str, Any]]:
    """OpenAI-style tool definitions for extension Eyes/Hands ops."""
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "observe",
                "description": "Observe the agent tab Eyes (targets, optional excerpt).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skip_screenshot": {"type": "boolean"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "click",
                "description": "Click by target_id from the latest observe.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "integer"},
                        "ref": {"type": "string"},
                        "text": {"type": "string"},
                        "contains": {"type": "string"},
                        "selector": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fill",
                "description": "Fill an input by target_id; optional press_key (e.g. Enter).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "integer"},
                        "value": {"type": "string"},
                        "press_key": {"type": "string"},
                        "ref": {"type": "string"},
                        "selector": {"type": "string"},
                    },
                    "required": ["value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "openTab",
                "description": "Open a URL in the agent tab context (never placement:human).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "placement": {"type": "string"},
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "duplicateTab",
                "description": "Duplicate a tab for agent work.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tab_id": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "probe_links",
                "description": "Probe link affordances when Eyes lack structure (not ritual).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "probe_form",
                "description": "Probe form fields on the page.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "probe_table",
                "description": "Probe table structure on the page.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "press_key",
                "description": "Send a key to the focused element / page.",
                "parameters": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scroll",
                "description": "Scroll the page or a scroll container.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string"},
                        "target_id": {"type": "integer"},
                        "delta_y": {"type": "number"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "closeTab",
                "description": "Close a tab by tab_id.",
                "parameters": {
                    "type": "object",
                    "properties": {"tab_id": {"type": "integer"}},
                    "required": ["tab_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scrape",
                "description": "Scrape excerpt/links from the agent tab.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mint_item",
                "description": "Mint a child You/Agent/Waiting item (park or subtask).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "parent_id": {"type": "string"},
                        "column": {"type": "string"},
                        "title": {"type": "string"},
                        "status": {"type": "string"},
                        "park_kind": {"type": "string"},
                        "resume": {"type": "boolean"},
                        "source": {"type": "object"},
                        "hints": {"type": "object"},
                    },
                    "required": ["column", "title"],
                },
            },
        },
    ]
    if include_complete_item:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "complete_item",
                    "description": (
                        "Mark one Agent root finished for this Run tab "
                        "(done summary or Partial). Advances remaining_ids."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "item_id": {"type": "string"},
                            "summary": {"type": "string"},
                            "outcome": {
                                "type": "string",
                                "description": "done | partial",
                            },
                        },
                        "required": ["item_id", "summary"],
                    },
                },
            }
        )
    return tools


async def _complete_run_tab_item(
    args: dict[str, Any],
    *,
    item: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Patch one Agent item and advance run_state remaining_ids."""
    from .app import _active_item_by_run, _patch_work_item, _work_items, get_config
    from .execute_validation import (
        auth_gate_blocks_false_closure,
        execute_summary_incomplete_reason,
        execute_summary_indicates_failure,
        human_judgment_blocks_false_closure,
        open_auth_gate_you,
        open_you_remainder,
    )
    from .observability import record

    def _sync_active(next_id: str | None) -> None:
        if run_id and next_id:
            _active_item_by_run[run_id] = next_id

    run_state = ctx.get("run_state")
    if not isinstance(run_state, dict):
        return {"ok": False, "op": "complete_item", "error": "not in run_tab mode"}
    run_id = str(ctx.get("run_id") or "")
    item_id = str(args.get("item_id") or run_state.get("current_item_id") or "")
    summary = str(args.get("summary") or "").strip()
    outcome = str(args.get("outcome") or "done").strip().lower()
    if not item_id:
        return {"ok": False, "op": "complete_item", "error": "missing item_id"}
    if item_id not in (run_state.get("remaining_ids") or []):
        return {
            "ok": False,
            "op": "complete_item",
            "error": f"item {item_id} not in remaining_ids",
        }
    if not summary:
        return {"ok": False, "op": "complete_item", "error": "missing summary"}

    cfg = get_config()
    target = (run_state.get("items_by_id") or {}).get(item_id) or item
    gate_you = open_auth_gate_you(item_id, _work_items)
    remainder_you = open_you_remainder(item_id, _work_items)

    if outcome == "partial" or execute_summary_indicates_failure(summary):
        err = summary if summary.lower().startswith("partial:") else f"Partial: {summary}"
        await _patch_work_item(
            item_id, status="failed", run_id=run_id, last_error=err[:500]
        )
        rem = [x for x in run_state["remaining_ids"] if x != item_id]
        run_state["remaining_ids"] = rem
        run_state["failed_ids"] = list(run_state.get("failed_ids") or []) + [item_id]
        run_state["current_item_id"] = rem[0] if rem else None
        ctx["remaining_ids"] = rem
        ctx["current_item_id"] = run_state["current_item_id"]
        _sync_active(run_state["current_item_id"])
        record(
            "agent.item_progress",
            run_id,
            cfg=cfg,
            item_id=item_id,
            error=err[: cfg.prompts.event_snippet_max_chars],
            flags={"outcome": "partial"},
        )
        return {
            "ok": True,
            "op": "complete_item",
            "item_id": item_id,
            "outcome": "partial",
            "remaining_ids": rem,
            "current_item_id": run_state["current_item_id"],
        }

    incomplete = execute_summary_incomplete_reason(summary)
    if not incomplete:
        incomplete = auth_gate_blocks_false_closure(
            summary, has_auth_gate_you=bool(gate_you or remainder_you)
        )
    if not incomplete:
        incomplete = human_judgment_blocks_false_closure(
            summary,
            item_title=str(target.get("title") or ""),
            has_you_remainder=bool(remainder_you or gate_you),
        )
    if incomplete and gate_you:
        # Parked for auth — pause run instead of failing the item.
        run_state["paused"] = True
        await _patch_work_item(item_id, status="awaiting_human", run_id=run_id)
        record(
            "agent.item_progress",
            run_id,
            cfg=cfg,
            item_id=item_id,
            flags={"outcome": "awaiting_human"},
        )
        return {
            "ok": True,
            "op": "complete_item",
            "item_id": item_id,
            "outcome": "awaiting_human",
            "paused": True,
            "remaining_ids": list(run_state.get("remaining_ids") or []),
        }
    if incomplete:
        err = incomplete if incomplete.lower().startswith("partial:") else f"Partial: {incomplete}"
        await _patch_work_item(
            item_id, status="failed", run_id=run_id, last_error=err[:500]
        )
        rem = [x for x in run_state["remaining_ids"] if x != item_id]
        run_state["remaining_ids"] = rem
        run_state["failed_ids"] = list(run_state.get("failed_ids") or []) + [item_id]
        run_state["current_item_id"] = rem[0] if rem else None
        ctx["remaining_ids"] = rem
        ctx["current_item_id"] = run_state["current_item_id"]
        _sync_active(run_state["current_item_id"])
        record(
            "agent.item_progress",
            run_id,
            cfg=cfg,
            item_id=item_id,
            error=err[: cfg.prompts.event_snippet_max_chars],
            flags={"outcome": "incomplete"},
        )
        return {
            "ok": False,
            "op": "complete_item",
            "item_id": item_id,
            "error": err,
            "remaining_ids": rem,
            "current_item_id": run_state["current_item_id"],
        }

    # Done — if You remainder parked, still mark done with evidence.
    evidence = {"summary": summary[: cfg.prompts.execute_summary_max_chars]}
    status = "awaiting_human" if gate_you else "done"
    await _patch_work_item(
        item_id,
        status=status,
        run_id=run_id,
        evidence=evidence,
        clear_last_error=True,
    )
    rem = [x for x in run_state["remaining_ids"] if x != item_id]
    run_state["remaining_ids"] = rem
    run_state["completed_ids"] = list(run_state.get("completed_ids") or []) + [item_id]
    run_state["current_item_id"] = rem[0] if rem else None
    if gate_you:
        run_state["paused"] = True
    ctx["remaining_ids"] = rem
    ctx["current_item_id"] = run_state["current_item_id"]
    _sync_active(run_state["current_item_id"])
    record(
        "agent.item_progress",
        run_id,
        cfg=cfg,
        item_id=item_id,
        summary_snippet=summary[: cfg.prompts.event_summary_snippet_max_chars],
        flags={"outcome": status},
    )
    return {
        "ok": True,
        "op": "complete_item",
        "item_id": item_id,
        "outcome": status,
        "paused": bool(run_state.get("paused")),
        "remaining_ids": rem,
        "current_item_id": run_state["current_item_id"],
    }


async def run_host_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    item: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Execute one tool; returns a JSON-serializable payload for the transcript."""
    run_id = str(ctx.get("run_id") or item.get("run_id") or "")
    human_tab = ctx.get("human_tab_id") or item.get("human_tab_id")
    agent_tab = ctx.get("agent_tab_id") or item.get("agent_tab_id")
    cfg = load_config()
    args = arguments if isinstance(arguments, dict) else {}

    if name == "complete_item":
        try:
            return await _complete_run_tab_item(args, item=item, ctx=ctx)
        except HTTPException as exc:
            return {"ok": False, "op": "complete_item", "error": str(exc.detail)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "op": "complete_item", "error": str(exc)[:500]}

    if name == "mint_item":
        from .app import MintItemBody, mint_item

        parent_id = str(args.get("parent_id") or item.get("id") or "")
        body = MintItemBody(
            run_id=run_id,
            parent_id=parent_id,
            column=str(args.get("column") or "you"),
            title=str(args.get("title") or "Untitled"),
            status=str(args.get("status") or "proposed"),
            hints=args.get("hints") if isinstance(args.get("hints"), dict) else None,
            source=args.get("source") if isinstance(args.get("source"), dict) else None,
            park_kind=args.get("park_kind"),
            resume=args.get("resume"),
        )
        try:
            return await mint_item(body)
        except HTTPException as exc:
            return {"ok": False, "op": "mint_item", "error": str(exc.detail)}

    if name not in BROWSER_TOOL_NAMES:
        return {"ok": False, "op": name, "error": f"unknown tool: {name}"}

    from .app import dispatch_browser_command_and_wait

    params = dict(args)
    # Common fields that belong on the command envelope, not params.
    for key in ("url", "skip_screenshot", "placement"):
        pass
    command: dict[str, Any] = {
        "run_id": run_id,
        "op": name,
        "human_tab_id": human_tab,
        "tab_id": agent_tab,
        "handoff_url": ctx.get("handoff_url", ""),
        "wait": True,
        "wait_timeout_sec": cfg.host.browser_wait_timeout_sec,
        "count_evidence": True,
    }
    if name == "press_key":
        # Extension Hands op is ``key`` (tool name stays press_key for the model).
        command["op"] = "key"
        key = params.pop("key", None) or params.pop("press_key", None)
        if key is not None:
            params["key"] = key
    if name == "openTab":
        command["url"] = params.pop("url", None)
        if params.get("placement"):
            command.setdefault("params", {})
        # keep placement in params for policy
    if name == "duplicateTab" and params.get("tab_id") is not None:
        command["tab_id"] = params.get("tab_id")
    closed_tab_id = None
    if name == "closeTab" and params.get("tab_id") is not None:
        closed_tab_id = params.pop("tab_id")
        command["tab_id"] = closed_tab_id
    if name == "observe" and "skip_screenshot" in params:
        command["skip_screenshot"] = bool(params.pop("skip_screenshot"))
    elif cfg.browser.observe_skip_screenshot_default and name in (
        "observe",
        "click",
        "fill",
        "scrape",
    ):
        command["skip_screenshot"] = True

    if params:
        command["params"] = params

    try:
        result = await dispatch_browser_command_and_wait(
            command,
            timeout=float(command.get("wait_timeout_sec") or cfg.host.browser_wait_timeout_sec),
        )
    except Exception as exc:  # noqa: BLE001 — surface to model
        return {"ok": False, "op": name, "error": str(exc)[:500]}

    # Update agent_tab_id if open/duplicate returned a new tab
    if isinstance(result, dict):
        new_tab = result.get("tab_id") or (result.get("observe") or {}).get("tab_id")
        if name in ("openTab", "duplicateTab") and new_tab is not None:
            ctx["agent_tab_id"] = new_tab
        if name == "closeTab" and result.get("ok", True):
            closed = closed_tab_id if closed_tab_id is not None else result.get("tab_id")
            if closed is not None and ctx.get("agent_tab_id") == closed:
                ctx["agent_tab_id"] = None
        return {"ok": result.get("ok", True), "op": name, "result": result}
    return {"ok": True, "op": name, "result": result}


def tool_calls_for_api(tool_calls: list[Any]) -> list[dict[str, Any]]:
    """Serialize ToolCall dataclasses to OpenAI message tool_calls shape."""
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        out.append(
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments or {}),
                },
            }
        )
    return out
