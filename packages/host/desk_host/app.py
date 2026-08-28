"""FastAPI application and WebSocket hub."""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .backends import get_backend, new_run_id
from .calendar import book_calendar_slot
from .config import config_for_extension, load_config
from .navigation import normalize_browser_command
from .observability import emit
from .policy import policy_denied_reason
from .screenshot_store import persist_screenshot

# In-memory proposal + extension connection state
_proposals: dict[str, dict[str, Any]] = {}
_handoff_urls: dict[str, str] = {}
_screenshot_counts: dict[str, int] = {}
_config_cache = None
_extension_ws: WebSocket | None = None
_extension_connected = False
_pending_commands: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
_command_results: dict[str, dict[str, Any]] = {}
_command_waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}

SCREENSHOT_OPS = frozenset(
    {"click", "fill", "scroll", "scrape", "screenshot", "openTab", "duplicateTab"}
)


def get_config():
    global _config_cache
    if _config_cache is None:
        _config_cache = load_config()
    return _config_cache


def reset_config_cache() -> None:
    global _config_cache
    _config_cache = None


class HandoffBody(BaseModel):
    run_id: str | None = None
    url: str
    title: str | None = None
    selection: str | None = None
    human_tab_id: int
    window_id: int
    intent: str | None = None
    snapshot: dict[str, Any] | None = None


class AcceptBody(BaseModel):
    run_id: str
    proposal_id: str
    work_item_id: str


class DenyBody(BaseModel):
    run_id: str
    proposal_id: str
    reason: str | None = None


class BrowserCommandBody(BaseModel):
    run_id: str
    command_id: str | None = None
    op: str
    url: str | None = None
    handoff_url: str | None = None
    tab_id: int | None = None
    human_tab_id: int | None = None
    params: dict[str, Any] | None = None
    wait: bool = False
    wait_timeout_sec: float = Field(default=30.0, ge=1.0, le=120.0)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="Virgil Desk Host", version="0.1.0", lifespan=lifespan)


@app.get("/v1/config")
async def get_desk_config() -> dict[str, Any]:
    return config_for_extension(get_config())


@app.get("/v1/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "0.1.0",
        "agent_backend": os.environ.get("DESK_AGENT_BACKEND", "mock"),
        "extension_connected": _extension_connected,
        "policy_version": "1",
    }


@app.post("/v1/handoff")
async def handoff_rest(body: HandoffBody) -> dict[str, Any]:
    return await _handle_handoff(body.model_dump())


async def _handle_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("url"):
        raise HTTPException(status_code=400, detail="url required")
    run_id = payload.get("run_id") or new_run_id()
    payload["run_id"] = run_id
    _handoff_urls[run_id] = str(payload.get("url") or "")
    emit("handoff.started", run_id, {"url": payload.get("url")})
    backend = get_backend()
    result = await backend.decompose(payload)
    emit(
        "handoff.decomposed",
        run_id,
        {
            "item_count": len(result.get("items", [])),
            "live": result.get("live"),
            "backend": os.environ.get("DESK_AGENT_BACKEND", "mock"),
        },
    )
    patch_id = uuid.uuid4().hex
    ops = [{"op": "add", "item": item} for item in result.get("items", [])]
    await _send_to_extension(
        {
            "type": "board_patch",
            "run_id": run_id,
            "patch_id": patch_id,
            "ops": ops,
        }
    )
    for item in result.get("items", []):
        item["run_id"] = run_id
        for prop in item.get("proposals") or []:
            _proposals[prop["id"]] = {**prop, "work_item_id": item["id"], "run_id": run_id}
    return result


async def _send_to_extension(message: dict[str, Any]) -> None:
    if _extension_ws is None:
        return
    await _extension_ws.send_json(message)


def reset_state_for_tests() -> None:
    """Clear in-memory hub state between tests."""
    global _extension_ws, _extension_connected
    _proposals.clear()
    _handoff_urls.clear()
    _screenshot_counts.clear()
    _command_results.clear()
    for fut in list(_command_waiters.values()):
        if not fut.done():
            fut.cancel()
    _command_waiters.clear()
    _extension_ws = None
    _extension_connected = False
    reset_config_cache()


@app.post("/v1/items/{item_id}/accept")
async def accept_item(item_id: str, body: AcceptBody) -> dict[str, Any]:
    prop = _proposals.get(body.proposal_id)
    if not prop:
        raise HTTPException(status_code=404, detail="proposal not found")
    emit(
        "proposal.accepted",
        body.run_id,
        {"proposal_id": body.proposal_id, "kind": prop.get("kind")},
    )
    committed: dict[str, Any] = {"kind": prop.get("kind")}
    if prop.get("kind") == "calendar_slot":
        committed.update(book_calendar_slot(prop.get("payload") or {}))
    return {"ok": True, "work_item_id": item_id, "status": "done", "committed": committed}


@app.post("/v1/browser")
async def browser_command(body: BrowserCommandBody) -> dict[str, Any]:
    """desk_browser tool entry — forwards BrowserOp to the extension."""
    cmd = body.model_dump(exclude={"wait", "wait_timeout_sec"})
    if not cmd.get("handoff_url") and cmd.get("run_id"):
        cmd["handoff_url"] = _handoff_urls.get(cmd["run_id"], "")
    cmd = normalize_browser_command(cmd)
    if not cmd.get("command_id"):
        cmd["command_id"] = uuid.uuid4().hex
    try:
        if body.wait:
            if not _extension_connected:
                raise HTTPException(status_code=503, detail="extension not connected")
            result = await dispatch_browser_command_and_wait(
                cmd, timeout=body.wait_timeout_sec
            )
            return {"ok": True, "command_id": cmd["command_id"], "result": result}
        await dispatch_browser_command(cmd)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="command_result timeout") from exc
    return {"ok": True, "command_id": cmd["command_id"]}


@app.post("/v1/items/{item_id}/deny")
async def deny_item(item_id: str, body: DenyBody) -> dict[str, Any]:
    emit(
        "proposal.denied",
        body.run_id,
        {"proposal_id": body.proposal_id, "reason": body.reason},
    )
    return {"ok": True, "work_item_id": item_id, "status": "denied"}


@app.websocket("/v1/extension")
async def extension_ws(ws: WebSocket) -> None:
    global _extension_ws, _extension_connected
    await ws.accept()
    _extension_ws = ws
    _extension_connected = True
    try:
        while True:
            raw = await ws.receive_json()
            msg_type = raw.get("type")
            if msg_type == "register":
                await ws.send_json(
                    {
                        "type": "registered",
                        "ok": True,
                        "config": config_for_extension(get_config()),
                    }
                )
            elif msg_type == "handoff_started":
                handoff = raw.get("handoff") or {}
                result = await _handle_handoff(handoff)
                await ws.send_json({"type": "handoff_result", **result})
            elif msg_type == "command_result":
                result = raw.get("result") or {}
                cid = result.get("command_id")
                if cid:
                    _command_results[cid] = result
                    waiter = _command_waiters.pop(cid, None)
                    if waiter and not waiter.done():
                        waiter.set_result(result)
                emit(
                    "browser.command_result",
                    raw.get("run_id", ""),
                    {
                        "command_id": cid,
                        "ok": result.get("ok"),
                        "duration_ms": result.get("duration_ms"),
                        "screenshot_count": 1 if result.get("screenshot") else 0,
                        "scrape_bytes": len(result.get("scrape_excerpt") or ""),
                    },
                )
                cfg = get_config()
                if cfg.observability.persist_screenshots and result.get("screenshot"):
                    path = persist_screenshot(
                        raw.get("run_id", ""),
                        cid or "",
                        result["screenshot"],
                    )
                    if path:
                        result["screenshot_ref"] = path
            elif msg_type == "item_ack":
                pass
    except WebSocketDisconnect:
        pass
    finally:
        _extension_connected = False
        if _extension_ws is ws:
            _extension_ws = None


async def dispatch_browser_command(command: dict[str, Any]) -> None:
    command = normalize_browser_command(command)
    run_id = command.get("run_id", "")
    op = command.get("op", "")
    cfg = get_config()

    if op in SCREENSHOT_OPS and run_id:
        count = _screenshot_counts.get(run_id, 0)
        if count >= cfg.browser.screenshot_max_per_run:
            emit(
                "policy.denied",
                run_id,
                {"rule": "screenshot_cap", "op": op, "count": count},
            )
            raise PermissionError("screenshot_cap")
        _screenshot_counts[run_id] = count + 1

    reason = policy_denied_reason(
        command.get("op", ""),
        command.get("tab_id"),
        command.get("human_tab_id"),
    )
    if reason:
        emit(
            "policy.denied",
            command.get("run_id", ""),
            {"rule": reason, "op": command.get("op")},
        )
        raise PermissionError(reason)
    emit(
        "browser.command",
        command.get("run_id", ""),
        {
            "command_id": command.get("command_id"),
            "op": command.get("op"),
        },
    )
    await _send_to_extension({"type": "browser_command", "command": command})


async def dispatch_browser_command_and_wait(
    command: dict[str, Any],
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    cid = command.get("command_id") or uuid.uuid4().hex
    command["command_id"] = cid
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict[str, Any]] = loop.create_future()
    _command_waiters[cid] = fut
    try:
        await dispatch_browser_command(command)
        return await asyncio.wait_for(fut, timeout=timeout)
    finally:
        _command_waiters.pop(cid, None)
