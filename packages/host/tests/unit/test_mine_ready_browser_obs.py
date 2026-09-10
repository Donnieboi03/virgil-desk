"""Mine-ready item_id / op_seq / binding hints on browser.command(+result)."""

import pytest

from desk_host.app import (
    _active_item_by_run,
    _obs_from_pending_command,
    dispatch_browser_command,
    reset_config_cache,
    reset_state_for_tests,
)
from desk_host.observability import read_events


@pytest.mark.asyncio
async def test_browser_command_stamps_item_id_op_seq_and_hints(tmp_path, monkeypatch):
    monkeypatch.setenv("DESK_LOG_DIR", str(tmp_path / "logs"))
    reset_config_cache()
    reset_state_for_tests()

    sent: list[dict] = []

    class FakeWs:
        async def send_json(self, msg):
            sent.append(msg)

    import desk_host.app as app_mod

    app_mod._extension_connected = True
    app_mod._extension_ws = FakeWs()
    _active_item_by_run["desk_mine"] = "desk_mine_agent_0"

    await dispatch_browser_command(
        {
            "command_id": "c_mine_1",
            "run_id": "desk_mine",
            "op": "click",
            "tab_id": 7,
            "url": "https://mail.google.com/mail/u/0/#inbox",
            "human_tab_id": 1,
            "params": {"target_id": 3, "ref": "t14", "text": "Hello"},
        }
    )
    rows = read_events(run_id="desk_mine")
    cmds = [r for r in rows if r.get("kind") == "browser.command"]
    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd["item_id"] == "desk_mine_agent_0"
    assert cmd["op_seq"] == 1
    assert cmd["tab_id"] == 7
    assert cmd["target_id"] == 3
    assert cmd["ref"] == "t14"
    assert "mail.google.com" in cmd["url"]

    # Result path pulls pending meta + site_fingerprint (mirrors WS/harness record).
    extra = _obs_from_pending_command(
        "c_mine_1",
        run_id="desk_mine",
        result={"url": "https://mail.google.com/mail/u/0/#inbox"},
    )
    assert extra["item_id"] == "desk_mine_agent_0"
    assert extra["op_seq"] == 1
    assert extra["site_fingerprint"] == "mail.google.com/mail"

    # Second command increments op_seq for same item.
    await dispatch_browser_command(
        {
            "command_id": "c_mine_2",
            "run_id": "desk_mine",
            "op": "observe",
            "tab_id": 7,
            "human_tab_id": 1,
            "params": {},
        }
    )
    rows2 = read_events(run_id="desk_mine")
    cmds2 = [r for r in rows2 if r.get("kind") == "browser.command"]
    assert cmds2[-1]["op_seq"] == 2
