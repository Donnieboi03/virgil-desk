"""Mock extension WebSocket client for host integration/E2E tests."""

from __future__ import annotations

import threading
from typing import Any

from starlette.testclient import TestClient


def fake_screenshot() -> dict[str, Any]:
    return {
        "mime": "image/png",
        "base64": "iVBORw0KGgo=",
        "width": 640,
        "height": 480,
    }


def fake_command_result(command_id: str, *, op: str = "click") -> dict[str, Any]:
    return {
        "command_id": command_id,
        "ok": True,
        "url": "https://example.com/job/1",
        "title": "Job",
        "scrape_excerpt": "Apply now — example page text for verify.",
        "screenshot": fake_screenshot(),
        "duration_ms": 42,
        "op": op,
    }


class MockExtensionSession:
    """Acts as the Chrome extension on /v1/extension."""

    def __init__(self, client: TestClient) -> None:
        self._ws_ctx = client.websocket_connect("/v1/extension")
        self.ws = self._ws_ctx.__enter__()
        self.ws.send_json({"type": "register", "extension_version": "test"})
        reg = self.ws.receive_json()
        assert reg.get("type") == "registered"

    def close(self) -> None:
        self._ws_ctx.__exit__(None, None, None)

    def handoff(self, handoff: dict[str, Any]) -> dict[str, Any]:
        self.ws.send_json({"type": "handoff_started", "handoff": handoff})
        patch = self.ws.receive_json()
        assert patch["type"] == "board_patch", patch
        assert patch["ops"][0]["op"] == "clear", patch["ops"]
        result = self.ws.receive_json()
        assert result["type"] == "handoff_result", result
        return result

    def respond_next_browser_command(
        self,
        *,
        run_id: str,
        op: str = "click",
    ) -> dict[str, Any]:
        msg = self.ws.receive_json()
        assert msg["type"] == "browser_command", msg
        command = msg["command"]
        result = fake_command_result(command["command_id"], op=command.get("op", op))
        self.ws.send_json(
            {
                "type": "command_result",
                "run_id": run_id,
                "result": result,
            }
        )
        return {"command": command, "result": result}


def run_browser_wait(client: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    body = {**payload, "wait": True}
    holder: list[dict[str, Any]] = []
    err: list[BaseException] = []

    def _post() -> None:
        try:
            r = client.post("/v1/browser", json=body)
            holder.append({"status": r.status_code, "json": r.json()})
        except BaseException as exc:  # pragma: no cover
            err.append(exc)

    thread = threading.Thread(target=_post, daemon=True)
    thread.start()
    return {"thread": thread, "holder": holder, "err": err}
