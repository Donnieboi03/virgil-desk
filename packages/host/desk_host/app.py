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
from .observability import emit
from .policy import policy_denied_reason, requires_auto_verify

# In-memory proposal + extension connection state
_proposals: dict[str, dict[str, Any]] = {}
_extension_ws: WebSocket | None = None
_extension_connected = False
_pending_commands: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
_command_results: dict[str, dict[str, Any]] = {}


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="Virgil Desk Host", version="0.1.0", lifespan=lifespan)


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
    emit("handoff.started", run_id, {"url": payload.get("url")})
    backend = get_backend()
    result = await backend.decompose(payload)
    emit(
        "handoff.decomposed",
        run_id,
        {"item_count": len(result.get("items", []))},
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
        for prop in item.get("proposals") or []:
            _proposals[prop["id"]] = {**prop, "work_item_id": item["id"], "run_id": run_id}
    return result


async def _send_to_extension(message: dict[str, Any]) -> None:
    if _extension_ws is None:
        return
    await _extension_ws.send_json(message)


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
        committed["status"] = "booked_stub"
    return {"ok": True, "work_item_id": item_id, "status": "done", "committed": committed}


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
                await ws.send_json({"type": "registered", "ok": True})
            elif msg_type == "handoff_started":
                handoff = raw.get("handoff") or {}
                result = await _handle_handoff(handoff)
                await ws.send_json({"type": "handoff_result", **result})
            elif msg_type == "command_result":
                result = raw.get("result") or {}
                cid = result.get("command_id")
                if cid:
                    _command_results[cid] = result
                emit(
                    "browser.command_result",
                    raw.get("run_id", ""),
                    {
                        "command_id": cid,
                        "ok": result.get("ok"),
                        "duration_ms": result.get("duration_ms"),
                    },
                )
                op = raw.get("op")
                if op and requires_auto_verify(str(op)):
                    pass  # extension already chained verify
            elif msg_type == "item_ack":
                pass
    except WebSocketDisconnect:
        pass
    finally:
        _extension_connected = False
        if _extension_ws is ws:
            _extension_ws = None


async def dispatch_browser_command(command: dict[str, Any]) -> None:
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
