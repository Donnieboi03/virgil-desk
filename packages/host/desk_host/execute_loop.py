"""Host-owned execute loop with Eyes/tool-result prune (backend-agnostic)."""

from __future__ import annotations

from typing import Any

from .config import load_config
from .execute_errors import HostExecuteError
from .execute_tools import host_loop_tools, run_host_tool, tool_calls_for_api
from .execute_transcript import (
    append_assistant_tool_calls,
    append_tool_result,
    build_system_and_packet,
    prune_messages,
)
from .execute_validation import (
    execute_summary_incomplete_reason,
    execute_summary_indicates_failure,
)
from .model_client import ModelClient


def _merge_usage(
    total: dict[str, Any] | None, step: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not step:
        return total
    out = dict(total or {})
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in step and step[key] is not None:
            out[key] = int(out.get(key) or 0) + int(step[key])
    if step.get("cost_usd") is not None:
        try:
            out["cost_usd"] = float(out.get("cost_usd") or 0) + float(step["cost_usd"])
        except (TypeError, ValueError):
            pass
    return out or None


def get_model_client(provider: str) -> ModelClient:
    name = (provider or "openrouter").strip().lower()
    if name == "openrouter":
        from .model_openrouter import OpenRouterModelClient

        return OpenRouterModelClient()
    raise RuntimeError(f"unsupported execute.model_provider: {provider}")


async def run_host_execute_loop(
    item: dict[str, Any],
    ctx: dict[str, Any],
    *,
    model_client: ModelClient | None = None,
) -> dict[str, Any]:
    """
    Host-owned tool loop: ModelClient steps + browser/mint tools + Eyes prune.

    Returns ``{summary, exit_code, usage?}`` like HermesBackend.execute_item.
    """
    cfg = load_config()
    client = model_client or get_model_client(cfg.execute.model_provider)
    model = cfg.execute.model or cfg.hermes.execute_model
    max_steps = max(1, int(cfg.execute.max_steps))
    eyes_keep_last = max(0, int(cfg.execute.eyes_keep_last))

    # Initial scrape into Packet (same as Hermes path)
    from .app import dispatch_browser_command_and_wait

    run_id = ctx.get("run_id", "")
    human_tab = ctx.get("human_tab_id") or item.get("human_tab_id")
    agent_tab = ctx.get("agent_tab_id") or item.get("agent_tab_id")
    if human_tab is None or agent_tab is None:
        raise HostExecuteError("execute missing human_tab_id or agent_tab_id")

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

    excerpt_max = cfg.browser.scrape_excerpt_max_chars
    ctx = {
        **ctx,
        "initial_scrape": {
            "url": scrape.get("url"),
            "title": scrape.get("title"),
            "excerpt": (scrape.get("scrape_excerpt") or "")[:excerpt_max],
        },
    }

    messages = build_system_and_packet(item, ctx)
    tools = host_loop_tools()
    usage_total: dict[str, Any] | None = None
    summary_max = cfg.prompts.execute_summary_max_chars

    for _step in range(max_steps):
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
                payload = await run_host_tool(
                    tc.name,
                    tc.arguments,
                    item=item,
                    ctx=ctx,
                )
                append_tool_result(
                    messages,
                    tool_call_id=tc.id,
                    name=tc.name,
                    payload=payload if isinstance(payload, dict) else {"ok": False, "error": str(payload)},
                )
            continue

        text = (step.content or "").strip()
        if not text:
            raise HostExecuteError(
                "host_loop execute returned empty output",
                usage=usage_total,
                empty_output=True,
            )
        summary = text[:summary_max]
        if execute_summary_indicates_failure(summary):
            raise HostExecuteError(summary, usage=usage_total)
        incomplete = execute_summary_incomplete_reason(summary)
        if incomplete:
            raise HostExecuteError(
                incomplete
                if incomplete.lower().startswith("partial:")
                else f"Partial: {incomplete}",
                usage=usage_total,
            )
        out: dict[str, Any] = {"summary": summary, "exit_code": 0}
        if usage_total:
            out["usage"] = usage_total
        return out

    raise HostExecuteError(
        f"Partial: host_loop reached max_steps ({max_steps}) without Done",
        usage=usage_total,
    )
