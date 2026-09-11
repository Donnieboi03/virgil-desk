"""Unit tests for Run-tab host_loop."""

from __future__ import annotations

import json

import pytest

from desk_host.execute_errors import HostExecuteError
from desk_host.execute_run import run_host_execute_run_loop
from desk_host.execute_transcript import build_run_tab_messages
from desk_host.model_client import ModelStepResult, ToolCall


class ScriptedModelClient:
    def __init__(self, steps: list[ModelStepResult]) -> None:
        self.steps = list(steps)
        self.calls = 0

    async def complete(self, messages, tools, *, model):
        self.calls += 1
        if not self.steps:
            return ModelStepResult(content="Partial: out of script")
        return self.steps.pop(0)


def test_build_run_tab_messages_omits_run_state():
    msgs = build_run_tab_messages(
        {
            "run_id": "r1",
            "items": [{"id": "a", "title": "T"}],
            "remaining_ids": ["a"],
            "run_state": {"secret": True},
        }
    )
    assert msgs[0]["role"] == "system"
    assert "complete_item" in msgs[0]["content"]
    body = msgs[1]["content"]
    assert "secret" not in body
    assert "remaining_ids" in body


@pytest.mark.asyncio
async def test_run_tab_completes_two_items(monkeypatch):
    async def fake_dispatch(command, timeout=30.0):
        return {
            "ok": True,
            "url": "https://mail.example/inbox",
            "title": "Inbox",
            "scrape_excerpt": "hello",
        }

    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "dispatch_browser_command_and_wait", fake_dispatch)

    async def fake_patch(item_id, *, status, run_id, evidence=None, last_error=None, clear_last_error=False):
        app_mod._work_items[item_id] = {
            **(app_mod._work_items.get(item_id) or {"id": item_id}),
            "status": status,
            "run_id": run_id,
        }
        return app_mod._work_items[item_id]

    monkeypatch.setattr(app_mod, "_patch_work_item", fake_patch)
    app_mod._work_items.clear()

    items = [
        {"id": "a0", "title": "Skim newsletters", "column": "agent", "status": "running"},
        {"id": "a1", "title": "Check rate", "column": "agent", "status": "running"},
    ]
    for it in items:
        app_mod._work_items[it["id"]] = dict(it)

    client = ScriptedModelClient(
        [
            ModelStepResult(
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="complete_item",
                        arguments={
                            "item_id": "a0",
                            "summary": "Single closure: Reviewed newsletters; no further action.",
                        },
                    )
                ]
            ),
            ModelStepResult(
                tool_calls=[
                    ToolCall(
                        id="2",
                        name="complete_item",
                        arguments={
                            "item_id": "a1",
                            "summary": "Single closure: extracted Acme rate; no further action.",
                        },
                    )
                ]
            ),
        ]
    )
    out = await run_host_execute_run_loop(
        items,
        {
            "run_id": "r1",
            "human_tab_id": 1,
            "agent_tab_id": 2,
            "handoff_url": "https://mail.example/inbox",
        },
        model_client=client,
    )
    assert out["exit_code"] == 0
    assert set(out["completed_ids"]) == {"a0", "a1"}
    assert out["remaining_ids"] == []
    assert app_mod._work_items["a0"]["status"] == "done"
    assert app_mod._work_items["a1"]["status"] == "done"


@pytest.mark.asyncio
async def test_run_tab_rejects_free_text_with_remaining(monkeypatch):
    async def fake_dispatch(command, timeout=30.0):
        return {"ok": True, "url": "https://x", "scrape_excerpt": "e", "title": "t"}

    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "dispatch_browser_command_and_wait", fake_dispatch)

    with pytest.raises(HostExecuteError) as ei:
        await run_host_execute_run_loop(
            [{"id": "a0", "title": "T", "column": "agent"}],
            {"run_id": "r", "human_tab_id": 1, "agent_tab_id": 2},
            model_client=ScriptedModelClient(
                [ModelStepResult(content="Single closure: done; no further action.")]
            ),
        )
    assert "remaining" in str(ei.value).lower()
