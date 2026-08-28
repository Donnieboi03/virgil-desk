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


def test_ws_observe_returns_interact_targets():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/inbox",
                    "human_tab_id": 101,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            pending = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "observe",
                    "human_tab_id": 101,
                    "tab_id": 202,
                },
            )
            ext.respond_next_browser_command(run_id=run_id, op="observe")
            pending["thread"].join(timeout=5)
            assert pending["holder"][0]["status"] == 200
            body = pending["holder"][0]["json"]["result"]
            assert body.get("interact_targets")
            assert body.get("observe")
        finally:
            ext.close()


def test_ws_second_observe_same_url_omits_excerpt():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/inbox",
                    "human_tab_id": 101,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            url = "https://example.com/inbox"
            long_text = "inbox body " + ("z" * 100)

            first = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "observe",
                    "human_tab_id": 101,
                    "tab_id": 202,
                },
            )
            ext.respond_next_browser_command(
                run_id=run_id, op="observe", url=url, text=long_text
            )
            first["thread"].join(timeout=5)
            body1 = first["holder"][0]["json"]["result"]
            assert body1.get("text_omitted") is False
            assert len(body1.get("scrape_excerpt") or "") > 40
            assert body1.get("interact_targets")

            second = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "observe",
                    "human_tab_id": 101,
                    "tab_id": 202,
                },
            )
            ext.respond_next_browser_command(
                run_id=run_id, op="observe", url=url, text=long_text
            )
            second["thread"].join(timeout=5)
            body2 = second["holder"][0]["json"]["result"]
            assert body2.get("text_omitted") is True
            assert (body2.get("scrape_excerpt") or "") == ""
            assert body2.get("interact_targets")
            assert body2.get("observe", {}).get("text_omitted") is True
        finally:
            ext.close()
