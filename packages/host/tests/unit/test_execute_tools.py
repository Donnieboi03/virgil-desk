"""Unit tests for host_loop tool dispatch."""

from __future__ import annotations

import pytest

from desk_host import execute_tools


@pytest.mark.asyncio
async def test_press_key_maps_to_key_op(monkeypatch):
    seen: list[dict] = []

    async def fake_dispatch(command, timeout=30.0):
        seen.append(command)
        return {"ok": True, "op": "key", "tab_id": 2}

    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "dispatch_browser_command_and_wait", fake_dispatch)

    ctx = {"run_id": "r", "human_tab_id": 1, "agent_tab_id": 2}
    out = await execute_tools.run_host_tool(
        "press_key",
        {"key": "Enter"},
        item={"id": "a", "run_id": "r"},
        ctx=ctx,
    )
    assert out["ok"] is True
    assert seen[0]["op"] == "key"
    assert seen[0]["params"]["key"] == "Enter"


@pytest.mark.asyncio
async def test_close_tab_clears_agent_tab_id(monkeypatch):
    async def fake_dispatch(command, timeout=30.0):
        return {"ok": True, "op": "closeTab", "tab_id": command["tab_id"]}

    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "dispatch_browser_command_and_wait", fake_dispatch)

    ctx = {"run_id": "r", "human_tab_id": 1, "agent_tab_id": 42}
    out = await execute_tools.run_host_tool(
        "closeTab",
        {"tab_id": 42},
        item={"id": "a", "run_id": "r"},
        ctx=ctx,
    )
    assert out["ok"] is True
    assert ctx["agent_tab_id"] is None
