import os

import pytest
from starlette.testclient import TestClient

from desk_host.app import app, reset_state_for_tests
from desk_host.backends import get_backend

from helpers.mock_extension import MockExtensionSession, run_browser_wait


@pytest.fixture(autouse=True)
def _reset_hub_state():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


@pytest.fixture
def hermes_backend(monkeypatch):
    monkeypatch.setenv("DESK_AGENT_BACKEND", "hermes")
    return get_backend()


def test_hermes_live_decompose_mocked_run(hermes_backend, monkeypatch):
    import json

    from desk_host.backends.hermes import HermesBackend, HermesRunResult

    payload = json.dumps(
        {
            "decomposition": "Parse the listing; you decide on apply.",
            "items": [
                {"column": "agent", "title": "Summarize job requirements", "status": "running"},
                {"column": "you", "title": "Apply when satisfied", "status": "proposed"},
            ],
        }
    )

    async def fake_run(_self, _message: str, **kwargs) -> HermesRunResult:
        return HermesRunResult(stdout=payload, stderr="", exit_code=0)

    monkeypatch.setattr(HermesBackend, "_hermes_run", fake_run)

    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/jobs/1",
                    "title": "Engineer role",
                    "human_tab_id": 11,
                    "window_id": 1,
                }
            )
            titles = [i["title"] for i in result["items"]]
            assert "Summarize job requirements" in titles
            assert result.get("live") is True
        finally:
            ext.close()


def test_hermes_handoff_includes_calendar_proposal(hermes_backend, monkeypatch):
    from desk_host.backends.hermes import HermesBackend, HermesRunResult

    async def empty_run(_self, _message: str, **kwargs) -> HermesRunResult:
        return HermesRunResult(stdout="", stderr="", exit_code=0)

    monkeypatch.setattr(HermesBackend, "_hermes_run", empty_run)
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/app",
                    "human_tab_id": 11,
                    "window_id": 1,
                }
            )
            waiting = [i for i in result["items"] if i.get("column") == "waiting"]
            assert waiting, "Hermes backend should propose calendar slot"
            assert waiting[0]["proposals"][0]["kind"] == "calendar_slot"
        finally:
            ext.close()


def test_hermes_path_browser_click_returns_screenshot(hermes_backend):
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(
                {
                    "url": "https://example.com/app",
                    "human_tab_id": 11,
                    "window_id": 1,
                }
            )
            run_id = result["run_id"]
            pending = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "click",
                    "human_tab_id": 11,
                    "tab_id": 22,
                    "params": {"selector": "button"},
                },
            )
            ext.respond_next_browser_command(run_id=run_id)
            pending["thread"].join(timeout=5)
            assert pending["holder"][0]["status"] == 200
            assert pending["holder"][0]["json"]["result"]["screenshot"]["base64"]
        finally:
            ext.close()


def test_hermes_execute_invokes_browser_command(hermes_backend, monkeypatch):
    import json
    import threading
    from typing import Any

    from desk_host.backends.hermes import HermesBackend, HermesRunResult

    payload = json.dumps(
        {
            "decomposition": "Review the app page.",
            "items": [
                {"column": "agent", "title": "Summarize page", "status": "running"},
            ],
        }
    )

    async def fake_run(_self, _message: str, **kwargs) -> HermesRunResult:
        return HermesRunResult(stdout=payload, stderr="", exit_code=0)

    monkeypatch.setattr(HermesBackend, "_hermes_run", fake_run)

    async def fake_execute(_self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from desk_host.app import dispatch_browser_command_and_wait

        await dispatch_browser_command_and_wait(
            {
                "run_id": ctx["run_id"],
                "op": "scrape",
                "human_tab_id": ctx.get("human_tab_id"),
                "tab_id": ctx.get("agent_tab_id"),
            }
        )
        return {"summary": "observed page", "exit_code": 0}

    monkeypatch.setattr(HermesBackend, "execute_item", fake_execute)
    handoff = {
        "run_id": "desk_exec_test",
        "url": "https://example.com/app",
        "human_tab_id": 1,
        "agent_tab_id": 2,
        "window_id": 1,
    }
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            result = ext.handoff(handoff)
            agent = [i for i in result["items"] if i["column"] == "agent"][0]
            holder: list = []

            def _execute():
                r = client.post(
                    f"/v1/items/{agent['id']}/execute",
                    json={"run_id": "desk_exec_test"},
                )
                holder.append(r)

            thread = threading.Thread(target=_execute, daemon=True)
            thread.start()
            ext.respond_next_browser_command(run_id="desk_exec_test", op="scrape")
            thread.join(timeout=5)
            assert holder[0].status_code == 200
        finally:
            ext.close()


def test_execute_hermes_subprocess_does_not_block_browser(hermes_backend, monkeypatch):
    """While Hermes runs via thread pool, desk-browser POSTs must still reach the host."""
    import json
    import threading

    from desk_host.backends.hermes import HermesBackend, HermesRunResult

    subprocess_started = threading.Event()
    allow_finish = threading.Event()

    def slow_run_sync(cmd, *, env, timeout):
        if any("Execute one Virgil Desk" in str(part) for part in cmd):
            subprocess_started.set()
            assert allow_finish.wait(timeout=5)
            return HermesRunResult(stdout="Reviewed inbox thread.", stderr="", exit_code=0)
        stub = {
            "decomposition": "stub for test",
            "items": [
                {"column": "agent", "title": "Agent task", "status": "running"},
                {"column": "you", "title": "Review", "status": "proposed"},
            ],
        }
        return HermesRunResult(stdout=json.dumps(stub), stderr="", exit_code=0)

    monkeypatch.setattr(HermesBackend, "_hermes_run_sync", staticmethod(slow_run_sync))

    handoff = {
        "run_id": "desk_noblock",
        "url": "https://example.com/inbox",
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
            ext.respond_next_browser_command(run_id=run_id, op="scrape")
            assert subprocess_started.wait(timeout=5), "Hermes subprocess should start"

            pending = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "scrape",
                    "human_tab_id": 1,
                    "tab_id": 2,
                    "wait": True,
                    "wait_timeout_sec": 5,
                },
            )
            ext.respond_next_browser_command(run_id=run_id, op="scrape")
            pending["thread"].join(timeout=5)
            assert pending["holder"][0]["status"] == 200

            allow_finish.set()
            thread.join(timeout=5)
            assert holder
            assert holder[0].status_code == 200
            assert holder[0].json()["status"] == "done"
        finally:
            ext.close()
