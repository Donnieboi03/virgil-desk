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
            agents = [i for i in result["items"] if i.get("column") == "agent"]
            assert agents
            assert agents[0]["status"] in ("proposed", "running")
            # Optional agent_tab_id on handoff is for tests/mocks; real extension omits it.
            assert agents[0].get("human_tab_id") == 101

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


def test_handoff_without_agent_tab_id_still_decomposes():
    """E2E: handoff scrape-then-defer shape (no agent_tab_id) still boards items."""
    handoff_payload = {
        "run_id": "desk_e2e_defer001",
        "url": "https://example.com/job/1",
        "title": "Job posting",
        "human_tab_id": 101,
        "window_id": 1,
        "snapshot": {
            "excerpt": "Apply now",
            "links": [],
        },
    }
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(handoff_payload)
            agents = [i for i in result["items"] if i.get("column") == "agent"]
            assert agents
            assert agents[0].get("agent_tab_id") in (None, "")
            assert agents[0].get("human_tab_id") == 101
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


def test_handoff_seeds_notepad_and_execute_records_recent(monkeypatch):
    """E2E: memory_patch at handoff; execute appends global_recent."""
    import threading
    from typing import Any

    from desk_host.backends.mock import MockBackend

    captured: list[dict[str, Any]] = []

    async def capture_execute(_self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from desk_host.app import dispatch_browser_command_and_wait

        captured.append(ctx)
        await dispatch_browser_command_and_wait(
            {
                "run_id": ctx["run_id"],
                "op": "scrape",
                "human_tab_id": ctx.get("human_tab_id"),
                "tab_id": ctx.get("agent_tab_id") or 2,
            }
        )
        return {"summary": f"finished {item.get('title')}", "exit_code": 0}

    monkeypatch.setattr(MockBackend, "execute_item", capture_execute)

    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://mail.example.com/inbox",
                    "human_tab_id": 1,
                    "agent_tab_id": 2,
                    "window_id": 1,
                    "intent": "triage inbox",
                }
            )
            run_id = result["run_id"]
            assert ext.memory["by_run_id"][run_id]["mission"] == "triage inbox"
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            holder: list = []

            def _ex():
                holder.append(
                    client.post(
                        f"/v1/items/{agent['id']}/execute",
                        json={"run_id": run_id},
                    )
                )

            t = threading.Thread(target=_ex, daemon=True)
            t.start()
            ext.begin_execute()
            ext.respond_next_browser_command(run_id=run_id, op="scrape")
            finished = ext.finish_execute_messages()
            assert finished["cleanup"]["type"] == "execute_cleanup"
            t.join(timeout=5)
            assert holder[0].status_code == 200
            assert ext.memory["global_recent"]
            assert "finished" in ext.memory["global_recent"][0]["summary"]
            assert captured[0].get("run_notepad") is not None
        finally:
            ext.close()
