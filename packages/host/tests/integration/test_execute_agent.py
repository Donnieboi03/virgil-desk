"""Execute agent item → browser_command integration."""

import threading
from typing import Any

import pytest
from starlette.testclient import TestClient

from desk_host.app import app, reset_state_for_tests
from desk_host.backends.mock import MockBackend
from desk_host.memory import apply_memory_patch
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
            ext.respond_memory_get()
            for expected_op in ("scrape", "observe"):
                handled = ext.respond_next_browser_command(
                    run_id=run_id, op=expected_op
                )
                assert handled["command"]["op"] == expected_op
            patch = ext.ws.receive_json()
            assert patch["type"] == "board_patch"
            updated = patch["ops"][0]["item"]
            assert updated["status"] == "done"
            assert updated.get("evidence", {}).get("summary")
            mem = ext.receive_memory_patch()
            assert any(op.get("op") == "append_recent" for op in mem["ops"])
            assert ext.memory["global_recent"]
            thread.join(timeout=5)
            assert holder
            resp = holder[0]
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "done"
        finally:
            ext.close()


def test_execute_injects_recent_memory_into_ctx(monkeypatch):
    captured: list[dict] = []

    async def capture_execute(_self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from desk_host.app import dispatch_browser_command_and_wait

        captured.append(ctx)
        await dispatch_browser_command_and_wait(
            {
                "run_id": ctx["run_id"],
                "op": "scrape",
                "human_tab_id": ctx.get("human_tab_id"),
                "tab_id": ctx.get("agent_tab_id"),
            }
        )
        return {"summary": "used memory", "exit_code": 0}

    monkeypatch.setattr(MockBackend, "execute_item", capture_execute)
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com",
                    "human_tab_id": 1,
                    "agent_tab_id": 2,
                    "window_id": 1,
                    "intent": "triage",
                }
            )
            run_id = result["run_id"]
            assert run_id in ext.memory["by_run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]

            ext.memory = apply_memory_patch(
                ext.memory,
                [
                    {
                        "op": "append_recent",
                        "entry": {
                            "item_id": "prior",
                            "title": "Prior task",
                            "outcome": "done",
                            "summary": "already reviewed Jess folder",
                        },
                    }
                ],
            )

            holder: list = []

            def _execute():
                holder.append(
                    client.post(
                        f"/v1/items/{agent['id']}/execute",
                        json={"run_id": run_id},
                    )
                )

            thread = threading.Thread(target=_execute, daemon=True)
            thread.start()
            ext.respond_memory_get()
            ext.respond_next_browser_command(run_id=run_id, op="scrape")
            ext.ws.receive_json()  # board_patch
            ext.receive_memory_patch()
            thread.join(timeout=5)
            assert holder[0].status_code == 200
            assert captured
            assert captured[0].get("recent_executions")
            assert captured[0]["recent_executions"][0]["summary"].startswith("already")
            assert "run_notepad" in captured[0]
        finally:
            ext.close()

def test_execute_requires_extension_connected():
    with TestClient(app) as client:
        handoff = {
            "url": "https://example.com/job",
            "human_tab_id": 1,
            "window_id": 1,
        }
        result = client.post("/v1/handoff", json=handoff).json()
        agent = [i for i in result["items"] if i["column"] == "agent"][0]
        resp = client.post(
            f"/v1/items/{agent['id']}/execute",
            json={"run_id": result["run_id"]},
        )
        assert resp.status_code == 503


def test_execute_without_browser_evidence_fails(monkeypatch):
    async def noop_execute(_self, _item: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        return {"summary": "skipped browser", "exit_code": 0}

    monkeypatch.setattr(MockBackend, "execute_item", noop_execute)
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {"url": "https://example.com", "human_tab_id": 1, "window_id": 1}
            )
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            holder: list = []

            def _execute():
                holder.append(
                    client.post(
                        f"/v1/items/{agent['id']}/execute",
                        json={"run_id": result["run_id"]},
                    )
                )

            thread = threading.Thread(target=_execute, daemon=True)
            thread.start()
            ext.respond_memory_get()
            patch = ext.ws.receive_json()
            assert patch["ops"][0]["item"]["status"] == "failed"
            ext.receive_memory_patch()
            thread.join(timeout=5)
            assert holder[0].status_code == 422
        finally:
            ext.close()


def test_browser_post_without_extension_returns_503():
    with TestClient(app) as client:
        resp = client.post(
            "/v1/browser",
            json={
                "run_id": "desk_x",
                "op": "scrape",
                "human_tab_id": 1,
                "tab_id": 2,
                "wait": False,
            },
        )
        assert resp.status_code == 503


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
