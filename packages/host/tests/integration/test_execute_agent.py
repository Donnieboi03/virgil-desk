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
            assert captured[0].get("semantic_facts") == []
        finally:
            ext.close()


def test_execute_injects_semantic_facts_into_ctx(monkeypatch):
    from desk_host.memory import apply_semantic_patch, empty_semantic

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
        return {"summary": "used semantic", "exit_code": 0}

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
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            notepad_before = dict(ext.memory.get("by_run_id") or {})
            recent_before = list(ext.memory.get("global_recent") or [])

            ext.semantic = apply_semantic_patch(
                empty_semantic(),
                [
                    {
                        "op": "upsert_fact",
                        "key": "prefer_concise",
                        "value": "Prefer concise summaries",
                        "tags": ["user"],
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
            facts = captured[0].get("semantic_facts") or []
            assert facts
            assert facts[0]["key"] == "prefer_concise"
            assert "concise" in facts[0]["value"]
            assert ext.memory.get("by_run_id") == notepad_before or run_id in (
                ext.memory.get("by_run_id") or {}
            )
            # Semantic seed must not clear working/episodic SoT shape.
            assert "by_run_id" in ext.memory
            assert isinstance(ext.memory.get("global_recent"), list)
            assert recent_before == [] or isinstance(recent_before, list)
        finally:
            ext.close()


def test_semantic_memory_rest_patch_and_get():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            holder: list = []

            def _patch():
                holder.append(
                    client.patch(
                        "/v1/desk-memory/semantic",
                        json={
                            "op": "upsert_fact",
                            "key": "yc_no_false_close",
                            "value": "Do not single-closure YC picks",
                            "tags": ["decision"],
                        },
                    )
                )

            thread = threading.Thread(target=_patch, daemon=True)
            thread.start()
            ext.drain_semantic_patch_then_get()
            thread.join(timeout=5)
            assert holder[0].status_code == 200
            body = holder[0].json()
            assert body["ok"] is True
            keys = {f["key"] for f in body["semantic"]["facts"]}
            assert "yc_no_false_close" in keys

            holder2: list = []

            def _get():
                holder2.append(client.get("/v1/desk-memory/semantic"))

            thread2 = threading.Thread(target=_get, daemon=True)
            thread2.start()
            ext.respond_memory_get()
            thread2.join(timeout=5)
            assert holder2[0].status_code == 200
            assert "yc_no_false_close" in {
                f["key"] for f in holder2[0].json()["semantic"]["facts"]
            }

            holder3: list = []

            def _del():
                holder3.append(
                    client.patch(
                        "/v1/desk-memory/semantic",
                        json={"op": "delete_fact", "key": "yc_no_false_close"},
                    )
                )

            thread3 = threading.Thread(target=_del, daemon=True)
            thread3.start()
            ext.drain_semantic_patch_then_get()
            thread3.join(timeout=5)
            assert holder3[0].status_code == 200
            assert holder3[0].json()["semantic"]["facts"] == []
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


def test_auth_gate_mint_awaiting_and_complete_resumes_parent():
    """You auth_gate mint → parent awaiting_human; Mark done → proposed + resume_parent_id."""
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/inbox",
                    "human_tab_id": 1,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            patched = client.patch(
                f"/v1/items/{agent['id']}",
                json={"run_id": run_id, "agent_tab_id": 42},
            )
            assert patched.status_code == 200, patched.text
            ext.ws.receive_json()  # agent_tab board_patch

            mint = client.post(
                "/v1/items/mint",
                json={
                    "run_id": run_id,
                    "parent_id": agent["id"],
                    "column": "you",
                    "title": "Clear Recruit.net login",
                    "park_kind": "auth_gate",
                    "resume": True,
                    "source": {"url": "https://jobs.example.com/apply?cf=1"},
                },
            )
            assert mint.status_code == 200, mint.text
            you = mint.json()["item"]
            assert you["park_kind"] == "auth_gate"
            assert you["resume"] is True
            assert you.get("agent_tab_id") == 42
            patch = ext.ws.receive_json()
            assert patch["type"] == "board_patch"
            statuses = {
                (op.get("item") or {}).get("id"): (op.get("item") or {}).get("status")
                for op in patch.get("ops") or []
            }
            assert statuses.get(agent["id"]) == "awaiting_human"
            from desk_host import app as desk_app

            assert desk_app._work_items[agent["id"]]["status"] == "awaiting_human"

            custody = client.post(
                f"/v1/items/{you['id']}/tab_custody",
                json={
                    "run_id": run_id,
                    "action": "reveal",
                    "agent_tab_id": 42,
                    "viewport_shot": {"mime": "image/png", "base64": "abc"},
                    "flags": {"shot_skipped_inactive": False},
                },
            )
            assert custody.status_code == 200, custody.text

            done = client.post(
                f"/v1/items/{you['id']}/complete",
                json={
                    "run_id": run_id,
                    "viewport_shot": {"mime": "image/png", "base64": "xyz"},
                    "shot_on_agent_tab": True,
                },
            )
            assert done.status_code == 200, done.text
            body = done.json()
            assert body["resume_parent_id"] == agent["id"]
            parent = desk_app._work_items[agent["id"]]
            assert parent["status"] == "proposed"
            assert parent.get("resume_ready") is True
            gates = parent.get("cleared_gates") or []
            assert gates and gates[-1].get("you_item_id") == you["id"]
            assert "jobs.example.com/apply" in (gates[-1].get("url") or "")
        finally:
            ext.close()


def test_human_remainder_mint_does_not_copy_agent_tab_id():
    """human_remainder stays URL-first — no agent_tab_id stamp for Show-tab custody."""
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/inbox",
                    "human_tab_id": 1,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            client.patch(
                f"/v1/items/{agent['id']}",
                json={"run_id": run_id, "agent_tab_id": 99},
            )
            ext.ws.receive_json()

            mint = client.post(
                "/v1/items/mint",
                json={
                    "run_id": run_id,
                    "parent_id": agent["id"],
                    "column": "you",
                    "title": "Apply on careers site",
                    "park_kind": "human_remainder",
                    "source": {"url": "https://jobs.example.com/apply"},
                },
            )
            assert mint.status_code == 200, mint.text
            you = mint.json()["item"]
            assert you["park_kind"] == "human_remainder"
            assert you.get("agent_tab_id") in (None, "")
            ext.ws.receive_json()  # board_patch
        finally:
            ext.close()


def test_tab_custody_rejects_bad_action_and_missing_item():
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/inbox",
                    "human_tab_id": 1,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            client.patch(
                f"/v1/items/{agent['id']}",
                json={"run_id": run_id, "agent_tab_id": 7},
            )
            ext.ws.receive_json()
            mint = client.post(
                "/v1/items/mint",
                json={
                    "run_id": run_id,
                    "parent_id": agent["id"],
                    "column": "you",
                    "title": "Login",
                    "park_kind": "auth_gate",
                    "source": {"url": "https://example.com/login"},
                },
            )
            you_id = mint.json()["item"]["id"]
            ext.ws.receive_json()

            bad = client.post(
                f"/v1/items/{you_id}/tab_custody",
                json={"run_id": run_id, "action": "regroup", "agent_tab_id": 7},
            )
            assert bad.status_code == 400

            missing = client.post(
                "/v1/items/does_not_exist/tab_custody",
                json={"run_id": run_id, "action": "park", "agent_tab_id": 7},
            )
            assert missing.status_code == 404

            park = client.post(
                f"/v1/items/{you_id}/tab_custody",
                json={
                    "run_id": run_id,
                    "action": "park",
                    "agent_tab_id": 7,
                    "flags": {"shot_skipped_inactive": True},
                },
            )
            assert park.status_code == 200, park.text
            assert park.json()["action"] == "park"
        finally:
            ext.close()


def test_auth_gate_complete_without_viewport_shot_still_resumes():
    """Mark done without a shot still unblocks Resume."""
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/inbox",
                    "human_tab_id": 1,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            client.patch(
                f"/v1/items/{agent['id']}",
                json={"run_id": run_id, "agent_tab_id": 11},
            )
            ext.ws.receive_json()
            mint = client.post(
                "/v1/items/mint",
                json={
                    "run_id": run_id,
                    "parent_id": agent["id"],
                    "column": "you",
                    "title": "Clear gate",
                    "park_kind": "auth_gate",
                    "source": {"url": "https://example.com/auth"},
                },
            )
            you_id = mint.json()["item"]["id"]
            ext.ws.receive_json()

            done = client.post(
                f"/v1/items/{you_id}/complete",
                json={"run_id": run_id, "shot_on_agent_tab": False},
            )
            assert done.status_code == 200, done.text
            assert done.json()["resume_parent_id"] == agent["id"]
            from desk_host import app as desk_app

            assert desk_app._work_items[agent["id"]].get("resume_ready") is True
        finally:
            ext.close()


def test_auth_gate_open_only_summary_stays_awaiting_not_failed(monkeypatch):
    """Incomplete open-only summary after auth_gate mint → awaiting_human, clears last_error."""

    async def open_only_execute(_self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
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
        return {"summary": "Opened YC Co-Founder Match recommendations.", "exit_code": 0}

    monkeypatch.setattr(MockBackend, "execute_item", open_only_execute)
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
                    "column": "you",
                    "title": "Log in to YC",
                    "park_kind": "auth_gate",
                    "resume": True,
                    "source": {"url": "https://www.startupschool.org/"},
                },
            )
            assert mint.status_code == 200, mint.text
            ext.ws.receive_json()  # mint board_patch

            from desk_host import app as desk_app

            desk_app._work_items[agent["id"]]["last_error"] = "stale Partial: leftover"

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
            assert updated["status"] == "awaiting_human"
            assert not updated.get("last_error")
            thread.join(timeout=5)
            assert holder[0].status_code == 200
            assert holder[0].json()["status"] == "awaiting_human"
            assert desk_app._work_items[agent["id"]]["status"] == "awaiting_human"
            assert "last_error" not in desk_app._work_items[agent["id"]]
            # Auth park must soft-end session (preserve agent tab for Show tab).
            assert finished["cleanup"]["type"] == "execute_session"
            assert finished["cleanup"].get("active") is False
        finally:
            ext.close()


def test_auth_gate_preserves_tab_when_execute_fails_no_browser_evidence(monkeypatch):
    """Early execute fail must not close agent tab if an auth_gate You is open."""

    async def no_browser_execute(_self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        # Deliberately skip desk-browser — triggers execute_require_browser_evidence.
        return {"summary": "minted You auth_gate then finished", "exit_code": 0}

    monkeypatch.setattr(MockBackend, "execute_item", no_browser_execute)
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
                    "column": "you",
                    "title": "Log in",
                    "park_kind": "auth_gate",
                    "resume": True,
                    "source": {"url": "https://example.com/login"},
                },
            )
            assert mint.status_code == 200, mint.text
            ext.ws.receive_json()  # mint board_patch

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
            # Failed path still emits board_patch + memory_patch + soft session end.
            finished = ext.finish_execute_messages()
            thread.join(timeout=5)
            assert holder[0].status_code == 422
            assert finished["cleanup"]["type"] == "execute_session"
            assert finished["cleanup"].get("active") is False
        finally:
            ext.close()


def test_execute_empty_title_does_not_500(monkeypatch):
    """Regression: empty title must not UnboundLocalError on human_judgment check."""

    async def ok_execute(_self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from desk_host.app import dispatch_browser_command_and_wait

        await dispatch_browser_command_and_wait(
            {
                "command_id": "c_empty_title",
                "run_id": ctx["run_id"],
                "op": "scrape",
                "human_tab_id": ctx["human_tab_id"],
                "tab_id": ctx["agent_tab_id"],
            }
        )
        return {
            "summary": "Verified expired link (deadline passed); no further action.",
            "exit_code": 0,
        }

    monkeypatch.setattr(MockBackend, "execute_item", ok_execute)
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/x",
                    "human_tab_id": 1,
                    "agent_tab_id": 2,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            from desk_host import app as desk_app

            desk_app._work_items[agent["id"]]["title"] = ""

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
            assert holder[0].status_code == 200, holder[0].text
            assert holder[0].json()["status"] == "done"
        finally:
            ext.close()


def test_execute_second_item_same_run_returns_409():
    """One active execute per run — overlapping Run agent must 409."""
    from desk_host import app as desk_app

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
                    "title": "Second agent task",
                },
            )
            assert mint.status_code == 200, mint.text
            ext.ws.receive_json()
            second_id = mint.json()["item"]["id"]

            desk_app._executing_run_ids[run_id] = agent["id"]
            desk_app._executing_item_ids.add(agent["id"])
            second = client.post(
                f"/v1/items/{second_id}/execute",
                json={"run_id": run_id},
            )
            assert second.status_code == 409, second.text
            assert "run" in second.json()["detail"].lower()
        finally:
            ext.close()
