import pytest

from desk_host.app import dispatch_browser_command, reset_state_for_tests
from desk_host.config import load_config

sent_commands: list[dict] = []


@pytest.fixture(autouse=True)
def _clean():
    reset_state_for_tests()
    sent_commands.clear()
    yield
    reset_state_for_tests()


@pytest.fixture(autouse=True)
def _capture_send(monkeypatch, fake_extension_connected):
    async def _capture(message: dict) -> bool:
        if message.get("type") == "browser_command":
            sent_commands.append(message["command"])
        return True

    monkeypatch.setattr("desk_host.app._send_to_extension", _capture)


@pytest.mark.asyncio
async def test_screenshot_cap_skips_instead_of_denying(monkeypatch):
    cfg = load_config()
    cfg.browser.screenshot_max_per_run = 2
    monkeypatch.setattr("desk_host.app.get_config", lambda: cfg)

    cmd_base = {
        "run_id": "desk_cap_test",
        "op": "screenshot",
        "tab_id": 10,
        "human_tab_id": 5,
    }
    for i in range(2):
        await dispatch_browser_command({**cmd_base, "command_id": f"c{i}"})

    await dispatch_browser_command({**cmd_base, "command_id": "c2"})
    assert sent_commands[-1].get("skip_screenshot") is True
