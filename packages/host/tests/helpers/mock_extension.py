"""Mock extension WebSocket client for host integration/E2E tests."""

from __future__ import annotations

import threading
from typing import Any

from starlette.testclient import TestClient

from desk_host.memory import apply_memory_patch, empty_memory


def fake_screenshot() -> dict[str, Any]:
    return {
        "mime": "image/png",
        "base64": "iVBORw0KGgo=",
        "width": 640,
        "height": 480,
    }


def fake_command_result(command_id: str, *, op: str = "click") -> dict[str, Any]:
    result: dict[str, Any] = {
        "command_id": command_id,
        "ok": True,
        "url": "https://example.com/job/1",
        "title": "Job",
        "scrape_excerpt": "Apply now — example page text for verify.",
        "screenshot": fake_screenshot(),
        "duration_ms": 42,
        "op": op,
    }
    if op == "observe":
        result["interact_targets"] = [
            {
                "id": 1,
                "ref": "t1",
                "kind": "clickable",
                "label": "Apply",
                "rect": {"x": 10, "y": 20, "w": 100, "h": 36},
                "center": {"x": 60, "y": 38},
            }
        ]
        result["observe"] = {
            "url": result["url"],
            "title": result["title"],
            "viewport": {"w": 1280, "h": 720},
            "device_pixel_ratio": 2,
            "text_excerpt": result["scrape_excerpt"],
            "interact_targets": result["interact_targets"],
            "scroll_containers": [],
        }
        result["viewport"] = {"w": 1280, "h": 720}
        result["device_pixel_ratio"] = 2
    elif op == "click":
        result["act_resolved"] = {
            "op": "click",
            "requested": {"target_id": 1},
            "used": "target_id",
            "hit": {"ref": "t1", "tag": "button", "center": {"x": 60, "y": 38}},
            "url_before": "https://example.com/job/1",
            "url_after": "https://example.com/job/1#applied",
        }
    return result


class MockExtensionSession:
    """Acts as the Chrome extension on /v1/extension."""

    def __init__(self, client: TestClient) -> None:
        self._ws_ctx = client.websocket_connect("/v1/extension")
        self.ws = self._ws_ctx.__enter__()
        self.ws.send_json({"type": "register", "extension_version": "test"})
        reg = self.ws.receive_json()
        assert reg.get("type") == "registered"
        self.memory: dict[str, Any] = empty_memory()
        self.messages: list[dict[str, Any]] = []

    def close(self) -> None:
        self._ws_ctx.__exit__(None, None, None)

    def handoff(self, handoff: dict[str, Any]) -> dict[str, Any]:
        self.ws.send_json({"type": "handoff_started", "handoff": handoff})
        patch = self.ws.receive_json()
        assert patch["type"] == "board_patch", patch
        assert patch["ops"][0]["op"] == "clear", patch["ops"]
        mem_patch = self.ws.receive_json()
        assert mem_patch["type"] == "memory_patch", mem_patch
        self.memory = apply_memory_patch(self.memory, mem_patch.get("ops") or [])
        self.messages.append(mem_patch)
        result = self.ws.receive_json()
        assert result["type"] == "handoff_result", result
        return result

    def respond_memory_get(self) -> dict[str, Any]:
        msg = self.ws.receive_json()
        assert msg["type"] == "memory_get", msg
        self.ws.send_json(
            {
                "type": "memory_snapshot",
                "request_id": msg["request_id"],
                "run_id": msg.get("run_id"),
                "memory": self.memory,
            }
        )
        self.messages.append(msg)
        return msg

    def receive_memory_patch(self) -> dict[str, Any]:
        msg = self.ws.receive_json()
        assert msg["type"] == "memory_patch", msg
        self.memory = apply_memory_patch(self.memory, msg.get("ops") or [])
        self.messages.append(msg)
        return msg

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
