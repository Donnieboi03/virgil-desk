import pytest
from starlette.testclient import TestClient

from desk_host.app import app, reset_state_for_tests

from helpers.mock_extension import MockExtensionSession


@pytest.fixture(autouse=True)
def _reset():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


def test_handoff_then_accept_calendar_proposal():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            handoff = client.post(
                "/v1/handoff",
                json={
                    "url": "https://example.com/calendar",
                    "human_tab_id": 9,
                    "window_id": 1,
                    "title": "Schedule",
                },
            )
            assert handoff.status_code == 200
            data = handoff.json()
            waiting = [i for i in data["items"] if i.get("proposals")]
            assert waiting, "mock backend should propose a calendar slot"
            item = waiting[0]
            assert item["column"] == "you"
            prop = item["proposals"][0]
            assert prop["kind"] == "calendar_slot"

            accept = client.post(
                f"/v1/items/{item['id']}/accept",
                json={
                    "run_id": data["run_id"],
                    "proposal_id": prop["id"],
                    "work_item_id": item["id"],
                },
            )
            assert accept.status_code == 200
            body = accept.json()
            assert body["ok"] is True
            assert body["committed"]["kind"] == "calendar_slot"
            assert body["committed"]["status"] == "booked_stub"
            assert body.get("needs_agent_tab") is False
            assert body.get("status") == "done"
        finally:
            ext.close()


def test_accept_ui_proposal_moves_to_agent_column():
    """Non-calendar Accept must land in Agent so Run agent / Run tab can execute."""
    import desk_host.app as app_mod

    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            run_id = "desk_ui_accept"
            item_id = "wi_ui_1"
            prop_id = "prop_ui_1"
            item = {
                "id": item_id,
                "column": "you",
                "status": "proposed",
                "title": "Confirm form",
                "run_id": run_id,
                "human_tab_id": 3,
                "proposals": [{"id": prop_id, "kind": "form_review", "payload": {}}],
            }
            app_mod._work_items[item_id] = item
            app_mod._proposals[prop_id] = {
                "id": prop_id,
                "kind": "form_review",
                "payload": {},
                "work_item_id": item_id,
                "run_id": run_id,
            }
            accept = client.post(
                f"/v1/items/{item_id}/accept",
                json={
                    "run_id": run_id,
                    "proposal_id": prop_id,
                    "work_item_id": item_id,
                },
            )
            assert accept.status_code == 200
            body = accept.json()
            assert body["needs_agent_tab"] is True
            assert body["status"] == "proposed"
            assert body["column"] == "agent"
            assert app_mod._work_items[item_id]["column"] == "agent"
            assert app_mod._work_items[item_id]["status"] == "proposed"
        finally:
            ext.close()


def test_deny_proposal():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            handoff = client.post(
                "/v1/handoff",
                json={
                    "url": "https://example.com/x",
                    "human_tab_id": 2,
                    "window_id": 1,
                },
            )
            data = handoff.json()
            you_prop = [i for i in data["items"] if i.get("proposals")][0]
            prop = you_prop["proposals"][0]
            deny = client.post(
                f"/v1/items/{you_prop['id']}/deny",
                json={
                    "run_id": data["run_id"],
                    "proposal_id": prop["id"],
                    "reason": "conflict",
                },
            )
            assert deny.status_code == 200
            assert deny.json()["status"] == "denied"
        finally:
            ext.close()
