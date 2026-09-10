"""Accept/deny board patch integration."""

import pytest
from starlette.testclient import TestClient

from desk_host.app import app, reset_state_for_tests

from helpers.mock_extension import MockExtensionSession


@pytest.fixture(autouse=True)
def _reset():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


def test_accept_patches_waiting_item_to_done():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/x",
                    "human_tab_id": 1,
                    "window_id": 1,
                }
            )
            waiting = [i for i in result["items"] if i["column"] == "waiting"][0]
            prop = waiting["proposals"][0]
            client.post(
                f"/v1/items/{waiting['id']}/accept",
                json={
                    "run_id": result["run_id"],
                    "proposal_id": prop["id"],
                    "work_item_id": waiting["id"],
                },
            )
            patch = ext.ws.receive_json()
            assert patch["type"] == "board_patch"
            assert patch["ops"][0]["op"] == "update"
            assert patch["ops"][0]["item"]["status"] == "done"
        finally:
            ext.close()
