"""Host-owned Run-tab execute: one host_loop over all proposed Agent items."""

from __future__ import annotations

from typing import Any

from .config import load_config
from .execute_errors import HostExecuteError
from .execute_tools import host_loop_tools, run_host_tool, tool_calls_for_api
from .execute_transcript import (
    append_assistant_tool_calls,
    append_tool_result,
    build_run_tab_messages,
    prune_messages,
)
from .execute_validation import (
    execute_summary_incomplete_reason,
    execute_summary_indicates_failure,
    open_auth_gate_you,
)
from .execute_loop import _merge_usage, get_model_client
from .model_client import ModelClient


def _slim_item(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "title",
        "column",
        "status",
        "hints",
        "source",
        "parent_id",
        "park_kind",
        "resume_ready",
        "cleared_gates",
    )
    return {k: item[k] for k in keys if k in item}


async def run_host_execute_run_loop(
    items: list[dict[str, Any]],
    ctx: dict[str, Any],
    *,
    model_client: ModelClient | None = None,
) -> dict[str, Any]:
    """
    One host_loop for a tab run. Model walks remaining_ids and calls complete_item
    after each Agent root. Returns summary/usage/paused/completed_ids.
    """
    if not items:
        raise HostExecuteError("execute run: no agent items")

    cfg = load_config()
    client = model_client or get_model_client(cfg.execute.model_provider)
    model = cfg.execute.model or cfg.hermes.execute_model
    eyes_keep_last = max(0, int(cfg.execute.eyes_keep_last))
    per_item = max(1, int(cfg.execute.max_steps))
    # Soft budget: base steps per item, capped so huge boards stay bounded.
    max_steps = min(per_item * len(items), per_item * 10)
    max_steps = max(per_item, max_steps)
    steps_per_item = max(8, per_item // 2)

    from .app import dispatch_browser_command_and_wait

    run_id = str(ctx.get("run_id") or "")
    human_tab = ctx.get("human_tab_id")
    agent_tab = ctx.get("agent_tab_id")
    if human_tab is None or agent_tab is None:
        raise HostExecuteError("execute run missing human_tab_id or agent_tab_id")

    scrape = await dispatch_browser_command_and_wait(
        {
            "run_id": run_id,
            "op": "scrape",
            "human_tab_id": human_tab,
            "tab_id": agent_tab,
            "handoff_url": ctx.get("handoff_url", ""),
            "count_evidence": False,
            "skip_screenshot": True,
        },
        timeout=cfg.host.browser_wait_timeout_sec,
    )
    if not scrape.get("ok", True):
        raise HostExecuteError(scrape.get("error") or "initial scrape failed")
    scrape_url = str(scrape.get("url") or "").strip()
    if scrape.get("tab_missing") or (not scrape_url and scrape.get("eyes_empty")):
        raise HostExecuteError(
            scrape.get("error")
            or "initial scrape: agent tab missing or empty (re-run / hand off again)"
        )
    if not scrape_url:
        raise HostExecuteError(
            "initial scrape: empty url (agent tab likely dead — re-run)"
        )

    excerpt_max = cfg.browser.scrape_excerpt_max_chars
    remaining_ids = [str(i["id"]) for i in items]
    items_by_id = {str(i["id"]): i for i in items}
    run_state: dict[str, Any] = {
        "remaining_ids": list(remaining_ids),
        "current_item_id": remaining_ids[0],
        "completed_ids": [],
        "failed_ids": [],
        "paused": False,
        "abort": False,
        "item_steps": {rid: 0 for rid in remaining_ids},
        "steps_per_item": steps_per_item,
        "items_by_id": items_by_id,
    }
    ctx = {
        **ctx,
        "mode": "run_tab",
        "run_state": run_state,
        "initial_scrape": {
            "url": scrape.get("url"),
            "title": scrape.get("title"),
            "excerpt": (scrape.get("scrape_excerpt") or "")[:excerpt_max],
        },
        "items": [_slim_item(i) for i in items],
        "remaining_ids": list(remaining_ids),
        "current_item_id": remaining_ids[0],
    }

    messages = build_run_tab_messages(ctx)
    tools = host_loop_tools(include_complete_item=True)
    usage_total: dict[str, Any] | None = None
    summary_max = cfg.prompts.execute_summary_max_chars
    anchor_item = items[0]

    for _step in range(max_steps):
        if ctx.get("_abort") or run_state.get("abort"):
            raise HostExecuteError("Partial: run tab cancelled")
        if run_state.get("paused"):
            out = {
                "summary": "Paused: awaiting human (auth gate) — Resume tab after Mark done",
                "exit_code": 0,
                "paused": True,
                "completed_ids": list(run_state.get("completed_ids") or []),
                "failed_ids": list(run_state.get("failed_ids") or []),
                "remaining_ids": list(run_state.get("remaining_ids") or []),
            }
            if usage_total:
                out["usage"] = usage_total
            return out
        if not run_state.get("remaining_ids"):
            summary = (
                f"Run tab complete: {len(run_state.get('completed_ids') or [])} done"
            )
            if run_state.get("failed_ids"):
                summary += f", {len(run_state['failed_ids'])} failed"
            out = {
                "summary": summary[:summary_max],
                "exit_code": 0,
                "paused": False,
                "completed_ids": list(run_state.get("completed_ids") or []),
                "failed_ids": list(run_state.get("failed_ids") or []),
                "remaining_ids": [],
            }
            if usage_total:
                out["usage"] = usage_total
            return out

        cur = str(run_state.get("current_item_id") or "")
        if cur:
            run_state["item_steps"][cur] = int(run_state["item_steps"].get(cur) or 0) + 1
            if run_state["item_steps"][cur] > steps_per_item:
                # Soft budget: force Partial on this member and advance.
                from .app import _patch_work_item
                from .observability import record as obs_record

                err = (
                    f"Partial: step budget ({steps_per_item}) exceeded for {cur}"
                )
                try:
                    await _patch_work_item(
                        cur, status="failed", run_id=run_id, last_error=err
                    )
                except Exception:  # noqa: BLE001
                    pass
                obs_record(
                    "agent.item_progress",
                    run_id,
                    cfg=cfg,
                    item_id=cur,
                    error=err,
                    flags={"outcome": "step_budget"},
                )
                rem = [x for x in run_state["remaining_ids"] if x != cur]
                run_state["remaining_ids"] = rem
                run_state["failed_ids"] = list(run_state.get("failed_ids") or []) + [cur]
                run_state["current_item_id"] = rem[0] if rem else None
                ctx["remaining_ids"] = rem
                ctx["current_item_id"] = run_state["current_item_id"]
                continue

        messages = prune_messages(messages, eyes_keep_last=eyes_keep_last)
        step = await client.complete(messages, tools, model=model)
        usage_total = _merge_usage(usage_total, step.usage)

        if step.tool_calls:
            append_assistant_tool_calls(
                messages,
                content=step.content,
                tool_calls=tool_calls_for_api(step.tool_calls),
            )
            for tc in step.tool_calls:
                # Bind tools to the current agent item for mint parent defaults.
                cur_id = str(run_state.get("current_item_id") or anchor_item["id"])
                cur_item = items_by_id.get(cur_id) or anchor_item
                payload = await run_host_tool(
                    tc.name,
                    tc.arguments,
                    item=cur_item,
                    ctx=ctx,
                )
                append_tool_result(
                    messages,
                    tool_call_id=tc.id,
                    name=tc.name,
                    payload=payload
                    if isinstance(payload, dict)
                    else {"ok": False, "error": str(payload)},
                )
                # Auth gate under current item → pause run.
                if open_auth_gate_you(cur_id, _work_items_snapshot()):
                    run_state["paused"] = True
            continue

        text = (step.content or "").strip()
        if not text:
            raise HostExecuteError(
                "host_loop execute run returned empty output",
                usage=usage_total,
                empty_output=True,
            )
        # Free-text Done only valid when no remaining items.
        if run_state.get("remaining_ids"):
            raise HostExecuteError(
                "Partial: run tab still has remaining items — call complete_item "
                "for each (or Partial: per item) before finishing",
                usage=usage_total,
            )
        if execute_summary_indicates_failure(text):
            raise HostExecuteError(text[:summary_max], usage=usage_total)
        incomplete = execute_summary_incomplete_reason(text)
        if incomplete:
            raise HostExecuteError(
                incomplete
                if incomplete.lower().startswith("partial:")
                else f"Partial: {incomplete}",
                usage=usage_total,
            )
        out = {
            "summary": text[:summary_max],
            "exit_code": 0,
            "paused": False,
            "completed_ids": list(run_state.get("completed_ids") or []),
            "failed_ids": list(run_state.get("failed_ids") or []),
            "remaining_ids": [],
        }
        if usage_total:
            out["usage"] = usage_total
        return out

    raise HostExecuteError(
        f"Partial: run tab reached max_steps ({max_steps}) with remaining "
        f"{run_state.get('remaining_ids')}",
        usage=usage_total,
    )


def _work_items_snapshot() -> dict[str, dict[str, Any]]:
    from . import app as app_mod

    return app_mod._work_items
