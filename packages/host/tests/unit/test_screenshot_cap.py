import pytest

from desk_host.app import app, dispatch_browser_command, reset_state_for_tests
from desk_host.config import load_config


@pytest.fixture(autouse=True)
def _clean():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


@pytest.mark.asyncio
async def test_screenshot_cap_denied(monkeypatch, fake_extension_connected):
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

    with pytest.raises(PermissionError, match="screenshot_cap"):
        await dispatch_browser_command({**cmd_base, "command_id": "c2"})
