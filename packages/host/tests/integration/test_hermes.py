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

    async def fake_run(_self, _message: str) -> HermesRunResult:
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

    async def empty_run(_self, _message: str) -> HermesRunResult:
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
