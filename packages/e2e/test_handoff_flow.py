"""E2E: mock extension drives full handoff → browser → screenshot path."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from desk_host.app import app, reset_state_for_tests
from helpers.mock_extension import MockExtensionSession, run_browser_wait


@pytest.fixture(autouse=True)
def _clean_state():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


def test_ws_handoff_board_patch_and_click_verify():
    handoff_payload = {
        "run_id": "desk_e2e001",
        "url": "https://example.com/job/1",
        "title": "Job posting",
        "human_tab_id": 101,
        "agent_tab_id": 202,
        "window_id": 1,
        "snapshot": {
            "excerpt": "Apply now — full page text for decompose.",
            "links": ["https://example.com/job/1/apply"],
            "screenshot": {
                "mime": "image/png",
                "base64": "iVBORw0KGgo=",
                "width": 800,
                "height": 600,
            },
        },
    }
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(handoff_payload)
            run_id = result["run_id"]
            assert len(result.get("items", [])) >= 1

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
            assert not pending["err"]
            assert pending["holder"]
            resp = pending["holder"][0]
            assert resp["status"] == 200
            body = resp["json"]
            assert body["ok"] is True
            assert body["result"]["screenshot"]["base64"]
            assert body["result"]["scrape_excerpt"]
        finally:
            ext.close()


def test_navigate_same_url_becomes_duplicate_tab():
    handoff_payload = {
        "url": "https://example.com/job/1",
        "human_tab_id": 5,
        "window_id": 1,
    }
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(handoff_payload)
            run_id = result["run_id"]

            pending = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "navigate",
                    "url": "https://example.com/job/1?ref=agent",
                    "human_tab_id": 5,
                },
            )
            handled = ext.respond_next_browser_command(run_id=run_id)
            assert handled["command"]["op"] == "duplicateTab"
            pending["thread"].join(timeout=5)
            assert pending["holder"][0]["status"] == 200
        finally:
            ext.close()


def test_navigate_different_url_becomes_open_tab():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/job/1",
                    "human_tab_id": 5,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            pending = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "navigate",
                    "url": "https://other.example.com/search",
                    "human_tab_id": 5,
                },
            )
            handled = ext.respond_next_browser_command(run_id=run_id)
            assert handled["command"]["op"] == "openTab"
            pending["thread"].join(timeout=5)
            assert pending["holder"][0]["status"] == 200
        finally:
            ext.close()


def test_calendar_accept_after_handoff():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/meet",
                    "human_tab_id": 3,
                    "window_id": 1,
                }
            )
            waiting = [i for i in result["items"] if i.get("column") == "waiting"][0]
            prop = waiting["proposals"][0]
            accept = client.post(
                f"/v1/items/{waiting['id']}/accept",
                json={
                    "run_id": result["run_id"],
                    "proposal_id": prop["id"],
                    "work_item_id": waiting["id"],
                },
            )
            assert accept.status_code == 200
            body = accept.json()
            assert body["committed"]["kind"] == "calendar_slot"
            assert body["committed"]["status"] == "booked_stub"
        finally:
            ext.close()
