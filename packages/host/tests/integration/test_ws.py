import pytest
from starlette.testclient import TestClient

from desk_host.app import app, reset_state_for_tests

from helpers.mock_extension import MockExtensionSession, run_browser_wait


@pytest.fixture(autouse=True)
def _reset_hub_state():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


def test_ws_handoff_and_click_with_screenshot():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/job/1",
                    "human_tab_id": 101,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            pending = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "click",
                    "human_tab_id": 101,
                    "tab_id": 202,
                    "params": {"selector": "button.apply"},
                },
            )
            ext.respond_next_browser_command(run_id=run_id)
            pending["thread"].join(timeout=5)
            assert pending["holder"][0]["status"] == 200
            assert pending["holder"][0]["json"]["result"]["screenshot"]
        finally:
            ext.close()
