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


def test_ws_command_result_logs_error_tab_url(tmp_path, monkeypatch):
    monkeypatch.setenv("DESK_LOG_DIR", str(tmp_path / "logs"))
    from desk_host.observability import read_events

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
                    "op": "openTab",
                    "human_tab_id": 101,
                    "tab_id": 202,
                    "url": "https://mail.google.com",
                },
            )
            ext.respond_next_browser_command(
                run_id=run_id,
                op="openTab",
                url="https://mail.google.com",
                ok=False,
                error="open failed",
            )
            pending["thread"].join(timeout=5)
            assert pending["holder"][0]["status"] == 200
            rows = [
                r
                for r in read_events(run_id=run_id)
                if r.get("kind") == "browser.command_result"
            ]
            assert rows
            last = rows[-1]
            assert last["flags"]["ok"] is False
            assert last.get("error") == "open failed"
            assert last.get("tab_id") == 202
            assert last.get("url") == "https://mail.google.com"
            assert last.get("op") == "openTab"
        finally:
            ext.close()


def test_ws_execute_cleanup_done_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("DESK_LOG_DIR", str(tmp_path / "logs"))
    from desk_host.observability import read_events

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
            ext.ws.send_json(
                {
                    "type": "execute_cleanup_done",
                    "run_id": run_id,
                    "item_id": "agent_0",
                    "closed_tab_ids": [10, 20],
                }
            )
            # Give the host receive loop a tick
            import time

            time.sleep(0.05)
            rows = [
                r
                for r in read_events(run_id=run_id)
                if r.get("kind") == "execute.cleanup_done"
            ]
            assert len(rows) == 1
            assert rows[0]["item_id"] == "agent_0"
            assert rows[0]["closed_tab_ids"] == [10, 20]
            assert rows[0]["measure"]["closed_tab_count"] == 2
        finally:
            ext.close()
