"""Mock extension WebSocket client for host integration/E2E tests."""

from __future__ import annotations

import threading
from typing import Any

from starlette.testclient import TestClient

from desk_host.memory import apply_memory_patch, empty_memory
from desk_host.observe_excerpt import decide_excerpt


def fake_screenshot() -> dict[str, Any]:
    return {
        "mime": "image/png",
        "base64": "iVBORw0KGgo=",
        "width": 640,
        "height": 480,
    }


def fake_command_result(
    command_id: str,
    *,
    op: str = "click",
    url: str = "https://example.com/job/1",
    text: str = "Apply now — example page text for verify.",
    last_full_text_url: str | None = None,
    full_max: int = 8000,
    followup_max: int = 4000,
    tab_id: int | None = 202,
    ok: bool = True,
    error: str | None = None,
) -> dict[str, Any]:
    excerpt = decide_excerpt(
        url=url,
        text=text,
        last_full_text_url=last_full_text_url,
        full_max=full_max,
        followup_max=followup_max,
    )
    result: dict[str, Any] = {
        "command_id": command_id,
        "ok": ok,
        "url": url,
        "title": "Job",
        "scrape_excerpt": excerpt["text"] if ok else "",
        "text_omitted": excerpt["text_omitted"] if ok else False,
        "excerpt_note": excerpt["note"] if ok else None,
        "screenshot": fake_screenshot() if ok else None,
        "duration_ms": 42,
        "op": op,
        "_next_baseline": excerpt["next_baseline"] if ok else None,
    }
    if tab_id is not None:
        result["tab_id"] = tab_id
    if error is not None:
        result["error"] = error
    if not ok:
        return result
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
            "text_omitted": excerpt["text_omitted"],
            "interact_targets": result["interact_targets"],
            "scroll_containers": [],
        }
        if excerpt["note"]:
            result["observe"]["excerpt_note"] = excerpt["note"]
        result["viewport"] = {"w": 1280, "h": 720}
        result["device_pixel_ratio"] = 2
    elif op == "click":
        result["act_resolved"] = {
            "op": "click",
            "requested": {"target_id": 1},
            "used": "target_id",
            "hit": {"ref": "t1", "tag": "button", "center": {"x": 60, "y": 38}},
            "url_before": url,
            "url_after": f"{url}#applied",
        }
    elif op == "fill":
        result["act_resolved"] = {
            "op": "fill",
            "requested": {"target_id": 3, "value": "ada@example.com"},
            "used": "target_id",
            "hit": {"ref": "t3", "tag": "input", "center": {"x": 80, "y": 40}},
            "url_before": url,
            "url_after": url,
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
        self._excerpt_baselines: dict[str, str] = {}

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

    def begin_execute(self) -> None:
        """memory_get reply + execute_session drain."""
        self.respond_memory_get()
        self.receive_execute_session()

    def finish_execute_messages(self) -> dict[str, Any]:
        """Drain board_patch → memory_patch → execute_cleanup (or soft session end)."""
        patch = self.ws.receive_json()
        assert patch["type"] == "board_patch", patch
        self.receive_memory_patch()
        end = self.ws.receive_json()
        assert end["type"] in ("execute_cleanup", "execute_session"), end
        if end["type"] == "execute_session":
            assert end.get("active") is False
        self.messages.append(end)
        return {"board_patch": patch, "cleanup": end}

    def receive_execute_session(self) -> dict[str, Any]:
        msg = self.ws.receive_json()
        assert msg["type"] == "execute_session", msg
        self.messages.append(msg)
        return msg

    def receive_execute_cleanup(self) -> dict[str, Any]:
        msg = self.ws.receive_json()
        assert msg["type"] == "execute_cleanup", msg
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
        url: str | None = None,
        text: str | None = None,
        ok: bool = True,
        error: str | None = None,
    ) -> dict[str, Any]:
        msg = self.ws.receive_json()
        assert msg["type"] == "browser_command", msg
        command = msg["command"]
        cmd_op = command.get("op", op)
        tab_id = command.get("tab_id")
        page_url = url or "https://example.com/job/1"
        page_text = text or ("Apply now — example page text for verify. " + ("x" * 200))
        baseline_key = f"{run_id}:{tab_id}"
        result = fake_command_result(
            command["command_id"],
            op=cmd_op,
            url=page_url,
            text=page_text,
            last_full_text_url=self._excerpt_baselines.get(baseline_key),
            full_max=8000,
            followup_max=40,
            tab_id=tab_id if tab_id is not None else 202,
            ok=ok,
            error=error,
        )
        next_base = result.pop("_next_baseline", None)
        if next_base and tab_id is not None:
            self._excerpt_baselines[baseline_key] = next_base
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
