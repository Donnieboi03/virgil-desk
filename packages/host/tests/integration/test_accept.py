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
            waiting = [i for i in data["items"] if i.get("column") == "waiting"]
            assert waiting, "mock backend should propose a calendar slot"
            item = waiting[0]
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
            waiting = [i for i in data["items"] if i.get("column") == "waiting"][0]
            prop = waiting["proposals"][0]
            deny = client.post(
                f"/v1/items/{waiting['id']}/deny",
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
