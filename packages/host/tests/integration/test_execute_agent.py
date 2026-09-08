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
            # Mock may still echo handoff agent_tab_id on items; real extension omits it.
            assert agent_items[0].get("human_tab_id") == 101
        finally:
            ext.close()


def test_handoff_without_agent_tab_defers_until_patch():
    """Handoff without agent_tab_id leaves items unprovisioned until PATCH (Run agent)."""
    handoff = {
        "run_id": "desk_defer_tabs001",
        "url": "https://example.com/job",
        "title": "Job",
        "human_tab_id": 101,
        "window_id": 1,
        "snapshot": {"excerpt": "Apply now", "links": []},
    }
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(handoff)
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            assert agent.get("agent_tab_id") in (None, "")
            assert agent.get("human_tab_id") == 101

            patched = client.patch(
                f"/v1/items/{agent['id']}",
                json={"run_id": run_id, "agent_tab_id": 303},
            )
            assert patched.status_code == 200
            assert patched.json()["item"]["agent_tab_id"] == 303
            tab_patch = ext.ws.receive_json()
            assert tab_patch["type"] == "board_patch"
            assert tab_patch["ops"][0]["item"]["agent_tab_id"] == 303

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
            ext.begin_execute()
            for expected_op in ("scrape", "observe"):
                handled = ext.respond_next_browser_command(
                    run_id=run_id, op=expected_op
                )
                assert handled["command"]["op"] == expected_op
                assert handled["command"].get("tab_id") == 303
            ext.finish_execute_messages()
            thread.join(timeout=5)
            assert holder[0].status_code == 200
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
            ext.begin_execute()
            for expected_op in ("scrape", "observe"):
                handled = ext.respond_next_browser_command(
                    run_id=run_id, op=expected_op
                )
                assert handled["command"]["op"] == expected_op
            finished = ext.finish_execute_messages()
            updated = finished["board_patch"]["ops"][0]["item"]
            assert updated["status"] == "done"
            assert updated.get("evidence", {}).get("summary")
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
            ext.begin_execute()
            ext.respond_next_browser_command(run_id=run_id, op="scrape")
            ext.finish_execute_messages()
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
            ext.begin_execute()
            finished = ext.finish_execute_messages()
            assert finished["board_patch"]["ops"][0]["item"]["status"] == "failed"
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



def test_execute_records_usage_measure(monkeypatch, tmp_path):
    """Injected backend usage lands on agent.executed / run.finished measure."""
    monkeypatch.setenv("DESK_LOG_DIR", str(tmp_path / "logs"))
    from desk_host.observability import read_events

    async def usage_execute(_self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from desk_host.app import dispatch_browser_command_and_wait

        await dispatch_browser_command_and_wait(
            {
                "run_id": ctx["run_id"],
                "op": "scrape",
                "human_tab_id": ctx.get("human_tab_id"),
                "tab_id": ctx.get("agent_tab_id") or 2,
                "count_evidence": True,
            }
        )
        return {
            "summary": f"Finished: {item.get('title')}",
            "exit_code": 0,
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
                "cost_usd": 0.04,
            },
        }

    monkeypatch.setattr(MockBackend, "execute_item", usage_execute)
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com",
                    "human_tab_id": 1,
                    "agent_tab_id": 2,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
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
            ext.begin_execute()
            ext.respond_next_browser_command(run_id=run_id, op="scrape")
            ext.finish_execute_messages()
            thread.join(timeout=5)
            assert holder[0].status_code == 200
            executed = [
                r for r in read_events(run_id=run_id) if r.get("kind") == "agent.executed"
            ]
            finished = [
                r for r in read_events(run_id=run_id) if r.get("kind") == "run.finished"
            ]
            assert executed
            assert executed[0]["measure"]["cost_usd"] == 0.04
            assert executed[0]["measure"]["prompt_tokens"] == 120
            assert finished
            assert finished[0]["measure"]["cost_usd"] == 0.04
        finally:
            ext.close()


def test_handoff_records_usage_measure(monkeypatch, tmp_path):
    monkeypatch.setenv("DESK_LOG_DIR", str(tmp_path / "logs"))
    from desk_host.observability import read_events

    original = MockBackend.decompose

    async def wrapped(self, handoff):
        out = await original(self, handoff)
        out["usage"] = {"prompt_tokens": 50, "cost_usd": 0.01}
        return out

    monkeypatch.setattr(MockBackend, "decompose", wrapped)
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com",
                    "human_tab_id": 1,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            rows = [
                r
                for r in read_events(run_id=run_id)
                if r.get("kind") == "handoff.decomposed"
            ]
            assert rows
            assert rows[0]["measure"]["item_count"] >= 1
            assert rows[0]["measure"]["prompt_tokens"] == 50
            assert rows[0]["measure"]["cost_usd"] == 0.01
        finally:
            ext.close()


def test_mint_item_board_patch_and_parent_done_blocked(monkeypatch):
    """mint_item adds child; parent execute stays running while agent child open."""

    async def quick_execute(_self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from desk_host.app import dispatch_browser_command_and_wait

        await dispatch_browser_command_and_wait(
            {
                "run_id": ctx["run_id"],
                "op": "scrape",
                "human_tab_id": ctx.get("human_tab_id"),
                "tab_id": ctx.get("agent_tab_id") or 2,
                "count_evidence": True,
            }
        )
        return {"summary": f"worked on {item.get('title')}", "exit_code": 0}

    monkeypatch.setattr(MockBackend, "execute_item", quick_execute)
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/inbox",
                    "human_tab_id": 1,
                    "agent_tab_id": 2,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            mint = client.post(
                "/v1/items/mint",
                json={
                    "run_id": run_id,
                    "parent_id": agent["id"],
                    "column": "agent",
                    "title": "Open nested Drive doc",
                },
            )
            assert mint.status_code == 200, mint.text
            child = mint.json()["item"]
            assert child["parent_id"] == agent["id"]
            assert child["kind"] == "subtask"
            patch = ext.ws.receive_json()
            assert patch["type"] == "board_patch"
            assert patch["ops"][0]["item"]["id"] == child["id"]

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
            ext.begin_execute()
            ext.respond_next_browser_command(run_id=run_id, op="scrape")
            finished = ext.finish_execute_messages()
            updated = finished["board_patch"]["ops"][0]["item"]
            assert updated["status"] == "running"
            assert "open agent children" in (updated.get("last_error") or "")
            assert finished["cleanup"]["type"] == "execute_session"
            assert finished["cleanup"].get("active") is False
            thread.join(timeout=5)
            assert holder[0].status_code == 200
            body = holder[0].json()
            assert body["status"] == "running"
            assert body["ok"] is False
        finally:
            ext.close()
