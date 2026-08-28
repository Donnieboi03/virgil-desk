"""Execute agent item → browser_command integration."""

import threading

import pytest
from starlette.testclient import TestClient

from desk_host.app import app, reset_state_for_tests
from helpers.mock_extension import MockExtensionSession, fake_screenshot, run_browser_wait


@pytest.fixture(autouse=True)
def _reset():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


def test_handoff_rich_snapshot_fields():
    handoff = {
        "run_id": "desk_richsnap001",
        "url": "https://mail.google.com/inbox",
        "title": "Inbox",
        "human_tab_id": 101,
        "agent_tab_id": 202,
        "window_id": 1,
        "snapshot": {
            "excerpt": "x" * 5000,
            "links": [f"https://example.com/{i}" for i in range(60)],
            "screenshot": fake_screenshot(),
        },
    }
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(handoff)
            assert result["run_id"] == "desk_richsnap001"
            agent_items = [i for i in result["items"] if i["column"] == "agent"]
            assert agent_items
            assert agent_items[0].get("agent_tab_id") == 202
        finally:
            ext.close()


def test_execute_agent_posts_browser_command_and_marks_done():
    handoff = {
        "url": "https://example.com/job",
        "human_tab_id": 1,
        "agent_tab_id": 2,
        "window_id": 1,
    }
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(handoff)
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]

            holder: list = []

            def _execute():
                r = client.post(
                    f"/v1/items/{agent['id']}/execute",
                    json={"run_id": run_id},
                )
                holder.append(r)

            thread = threading.Thread(target=_execute, daemon=True)
            thread.start()
            handled = ext.respond_next_browser_command(run_id=run_id, op="scrape")
            assert handled["command"]["op"] == "scrape"
            thread.join(timeout=5)
            assert holder
            resp = holder[0]
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "done"

            patch = ext.ws.receive_json()
            assert patch["type"] == "board_patch"
            assert patch["ops"][0]["item"]["status"] == "done"
        finally:
            ext.close()


def test_complete_you_item():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {"url": "https://example.com", "human_tab_id": 1, "window_id": 1}
            )
            you = [i for i in result["items"] if i["column"] == "you"][0]
            resp = client.post(
                f"/v1/items/{you['id']}/complete",
                json={"run_id": result["run_id"]},
            )
            assert resp.status_code == 200
            patch = ext.ws.receive_json()
            assert patch["ops"][0]["item"]["status"] == "done"
        finally:
            ext.close()
