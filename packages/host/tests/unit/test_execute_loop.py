"""Unit tests for Host-owned execute loop with mock ModelClient."""

from __future__ import annotations

import json

import pytest

from desk_host.execute_errors import HostExecuteError
from desk_host.execute_loop import run_host_execute_loop
from desk_host.model_client import ModelStepResult, ToolCall


class ScriptedModelClient:
    def __init__(self, steps: list[ModelStepResult]) -> None:
        self.steps = list(steps)
        self.calls = 0
        self.last_messages = None

    async def complete(self, messages, tools, *, model):
        self.last_messages = messages
        self.calls += 1
        if not self.steps:
            return ModelStepResult(content="Partial: out of script")
        return self.steps.pop(0)


@pytest.mark.asyncio
async def test_host_loop_two_tools_then_done(monkeypatch):
    async def fake_dispatch(command, timeout=30.0):
        op = command.get("op")
        if op == "scrape":
            return {
                "ok": True,
                "url": "https://mail.example/inbox",
                "title": "Inbox",
                "scrape_excerpt": "hello",
            }
        return {
            "ok": True,
            "op": op,
            "url": "https://mail.example/inbox",
            "interact_targets": [{"id": 1, "label": "Acme"}],
            "scrape_excerpt": "body",
        }

    monkeypatch.setattr(
        "desk_host.execute_loop.dispatch_browser_command_and_wait",
        fake_dispatch,
        raising=False,
    )
    # Patch where execute_tools imports it
    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "dispatch_browser_command_and_wait", fake_dispatch)

    client = ScriptedModelClient(
        [
            ModelStepResult(
                tool_calls=[
                    ToolCall(id="1", name="observe", arguments={}),
                ],
                usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            ),
            ModelStepResult(
                tool_calls=[
                    ToolCall(id="2", name="click", arguments={"target_id": 1}),
                ],
                usage={"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23},
            ),
            ModelStepResult(
                content="Verified expired link (deadline passed); no further action.",
                usage={"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
            ),
        ]
    )

    item = {
        "id": "desk_t_agent_0",
        "title": "Check thread",
        "column": "agent",
        "human_tab_id": 1,
        "agent_tab_id": 2,
        "run_id": "desk_t",
    }
    ctx = {
        "run_id": "desk_t",
        "human_tab_id": 1,
        "agent_tab_id": 2,
        "handoff_url": "https://mail.example/inbox",
    }
    out = await run_host_execute_loop(item, ctx, model_client=client)
    assert "Verified expired" in out["summary"]
    assert out["usage"]["prompt_tokens"] == 60
    assert client.calls == 3
    # Prune should have left tool messages in transcript
    roles = [m["role"] for m in client.last_messages or []]
    assert "tool" in roles


@pytest.mark.asyncio
async def test_host_loop_empty_output(monkeypatch):
    async def fake_dispatch(command, timeout=30.0):
        return {"ok": True, "url": "https://x", "scrape_excerpt": "e", "title": "t"}

    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "dispatch_browser_command_and_wait", fake_dispatch)

    client = ScriptedModelClient([ModelStepResult(content="")])
    item = {
        "id": "a",
        "title": "t",
        "human_tab_id": 1,
        "agent_tab_id": 2,
        "run_id": "r",
    }
    with pytest.raises(HostExecuteError) as ei:
        await run_host_execute_loop(
            item,
            {"run_id": "r", "human_tab_id": 1, "agent_tab_id": 2},
            model_client=client,
        )
    assert ei.value.empty_output is True


@pytest.mark.asyncio
async def test_host_loop_aborts_dead_tab_scrape(monkeypatch):
    async def fake_dispatch(command, timeout=30.0):
        return {
            "ok": False,
            "error": "No tab with id: 99.",
            "tab_id": 99,
        }

    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "dispatch_browser_command_and_wait", fake_dispatch)

    with pytest.raises(HostExecuteError) as ei:
        await run_host_execute_loop(
            {"id": "a", "title": "t", "human_tab_id": 1, "agent_tab_id": 99, "run_id": "r"},
            {"run_id": "r", "human_tab_id": 1, "agent_tab_id": 99},
            model_client=ScriptedModelClient([]),
        )
    assert "No tab" in str(ei.value)


@pytest.mark.asyncio
async def test_host_loop_aborts_eyes_empty_no_url(monkeypatch):
    async def fake_dispatch(command, timeout=30.0):
        return {
            "ok": True,
            "url": "",
            "title": "",
            "scrape_excerpt": "",
            "eyes_empty": True,
        }

    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "dispatch_browser_command_and_wait", fake_dispatch)

    with pytest.raises(HostExecuteError) as ei:
        await run_host_execute_loop(
            {"id": "a", "title": "t", "human_tab_id": 1, "agent_tab_id": 2, "run_id": "r"},
            {"run_id": "r", "human_tab_id": 1, "agent_tab_id": 2},
            model_client=ScriptedModelClient([]),
        )
    assert "agent tab" in str(ei.value).lower() or "scrape" in str(ei.value).lower()
