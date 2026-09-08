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
from .config import clear_config_cache, config_for_extension, load_config
from .harness_backend import (
    HarnessBackendError,
    is_harness_op,
    release_run as harness_release_run,
    reset_for_tests as harness_reset_for_tests,
    run_browser_op as harness_run_browser_op,
    uses_harness_driver,
)
from .memory import format_for_execute
from .navigation import normalize_browser_command
from .observability import browser_command_result_fields, measure_from_snapshot, record
from .policy import policy_denied_reason
from .execute_validation import (
    empty_probe_links_only_cover,
    execute_summary_incomplete_reason,
    parent_done_blocked_reason,
)
from .screenshot_store import persist_handoff_screenshot, persist_screenshot

# In-memory proposal + extension connection state
_proposals: dict[str, dict[str, Any]] = {}
_work_items: dict[str, dict[str, Any]] = {}
_handoff_urls: dict[str, str] = {}
_handoff_meta: dict[str, dict[str, Any]] = {}
_screenshot_counts: dict[str, int] = {}
_config_cache = None
_extension_ws: WebSocket | None = None
_extension_connected = False
_pending_commands: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
_command_results: dict[str, dict[str, Any]] = {}
_command_waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}
_memory_waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}
_browser_result_counts: dict[str, int] = {}
_command_evidence_flags: dict[str, bool] = {}
_execute_ops: dict[str, list[str]] = {}
_command_ops: dict[str, str] = {}
_last_probe_links_empty: dict[str, bool] = {}


class ExtensionNotConnectedError(Exception):
    """Raised when the Chrome extension WebSocket is not connected."""


def _require_extension() -> None:
    if not _extension_connected or _extension_ws is None:
        raise ExtensionNotConnectedError("extension not connected")

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
    clear_config_cache()


class HandoffBody(BaseModel):
    run_id: str | None = None
    url: str
    title: str | None = None
    selection: str | None = None
    human_tab_id: int
    agent_tab_id: int | None = None
    window_id: int
    intent: str | None = None
    snapshot: dict[str, Any] | None = None


class ExecuteBody(BaseModel):
    run_id: str


class ItemMetaBody(BaseModel):
    run_id: str
    agent_tab_id: int


class MintItemBody(BaseModel):
    run_id: str
    parent_id: str
    column: str
    title: str
    status: str = "proposed"
    hints: dict[str, Any] | None = None
    source: dict[str, Any] | None = None


class CompleteBody(BaseModel):
    run_id: str


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
    count_evidence: bool = True
    wait: bool = False
    wait_timeout_sec: float = Field(default=30.0, ge=1.0, le=120.0)
    skip_screenshot: bool | None = None


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
    _handoff_meta[run_id] = {
        "human_tab_id": payload.get("human_tab_id"),
        "agent_tab_id": payload.get("agent_tab_id"),
        "url": payload.get("url"),
    }
    snap = payload.get("snapshot") or {}
    cfg = get_config()
    record("handoff.started", run_id, cfg=cfg, url=payload.get("url"))
    measure, flags = measure_from_snapshot(snap)
    record(
        "handoff.snapshot",
        run_id,
        cfg=cfg,
        measure=measure,
        flags=flags,
        agent_tab_id=payload.get("agent_tab_id"),
    )
    backend = get_backend()
    result = await backend.decompose(payload)
    decompose_flags: dict[str, Any] | None = None
    if "live" in result:
        decompose_flags = {"live": bool(result["live"])}
    record(
        "handoff.decomposed",
        run_id,
        cfg=cfg,
        measure={"item_count": len(result.get("items", []))},
        flags=decompose_flags,
        backend=os.environ.get("DESK_AGENT_BACKEND", "mock"),
    )
    decomposition = str(result.get("decomposition") or "")
    _handoff_meta[run_id]["decomposition"] = decomposition
    patch_id = uuid.uuid4().hex
    ops: list[dict[str, Any]] = [{"op": "clear"}]
    ops.extend({"op": "add", "item": item} for item in result.get("items", []))
    await _send_board_patch(run_id, patch_id, ops)
    await _memory_patch(
        [
            {
                "op": "seed_run",
                "run_id": run_id,
                "decomposition": decomposition,
                "mission": str(payload.get("intent") or ""),
            }
        ]
    )
    for item in result.get("items", []):
        item["run_id"] = run_id
        meta = _handoff_meta.get(run_id, {})
        if meta.get("human_tab_id") is not None and item.get("human_tab_id") is None:
            item["human_tab_id"] = meta["human_tab_id"]
        if item.get("column") != "agent" and meta.get("agent_tab_id") is not None:
            item["agent_tab_id"] = meta["agent_tab_id"]
        _work_items[item["id"]] = item
        for prop in item.get("proposals") or []:
            _proposals[prop["id"]] = {**prop, "work_item_id": item["id"], "run_id": run_id}
    return result


async def _memory_get(run_id: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """Ask extension for virgil_desk_memory_v1 snapshot; empty on failure."""
    request_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict[str, Any]] = loop.create_future()
    _memory_waiters[request_id] = fut
    try:
        sent = await _send_to_extension(
            {
                "type": "memory_get",
                "request_id": request_id,
                "run_id": run_id,
            }
        )
        if not sent:
            return {"global_recent": [], "by_run_id": {}}
        snap = await asyncio.wait_for(fut, timeout=timeout)
        return snap.get("memory") or {"global_recent": [], "by_run_id": {}}
    except (asyncio.TimeoutError, ExtensionNotConnectedError):
        return {"global_recent": [], "by_run_id": {}}
    finally:
        _memory_waiters.pop(request_id, None)


async def _memory_patch(ops: list[dict[str, Any]]) -> bool:
    """Fire-and-forget memory_patch to extension (storage.local SoT)."""
    if not ops:
        return False
    return await _send_to_extension({"type": "memory_patch", "ops": ops})


async def _execute_cleanup(
    *,
    run_id: str,
    item_id: str,
    agent_tab_id: Any,
    human_tab_id: Any,
    preserve_tabs: bool = False,
) -> None:
    cfg = get_config()
    if uses_harness_driver(cfg.browser.driver) and not preserve_tabs:
        try:
            await asyncio.to_thread(
                harness_release_run,
                run_id,
                harness_bin=cfg.browser.harness_bin,
                bu_name=cfg.browser.harness_bu_name,
                timeout_sec=min(30.0, float(cfg.host.browser_wait_timeout_sec)),
            )
        except Exception:
            pass
    if preserve_tabs:
        # End execute session without closing tabs (parent still running with children).
        await _send_to_extension(
            {
                "type": "execute_session",
                "active": False,
                "run_id": run_id,
                "item_id": item_id,
            }
        )
        return
    await _send_to_extension(
        {
            "type": "execute_cleanup",
            "run_id": run_id,
            "item_id": item_id,
            "agent_tab_id": agent_tab_id,
            "human_tab_id": human_tab_id,
        }
    )


async def _execute_session_start(
    *,
    run_id: str,
    item_id: str,
    agent_tab_id: Any,
    human_tab_id: Any,
    handoff_url: str,
) -> None:
    await _send_to_extension(
        {
            "type": "execute_session",
            "active": True,
            "run_id": run_id,
            "item_id": item_id,
            "agent_tab_id": agent_tab_id,
            "human_tab_id": human_tab_id,
            "handoff_url": handoff_url,
        }
    )


async def _record_execute_memory(
    *,
    run_id: str,
    item: dict[str, Any],
    outcome: str,
    summary: str,
) -> None:
    cfg = get_config()
    title = str(item.get("title") or "")
    bullet = f"[{outcome}] {title}: {summary}".strip()
    await _memory_patch(
        [
            {
                "op": "append_recent",
                "entry": {
                    "run_id": run_id,
                    "item_id": item.get("id"),
                    "title": title,
                    "outcome": outcome,
                    "summary": summary[: cfg.prompts.event_summary_snippet_max_chars],
                },
            },
            {
                "op": "append_bullet",
                "run_id": run_id,
                "bullet": bullet[: cfg.memory.notepad_max_chars],
            },
        ]
    )


async def _send_board_patch(
    run_id: str,
    patch_id: str,
    ops: list[dict[str, Any]],
    *,
    required: bool = False,
) -> None:
    sent = await _send_to_extension(
        {
            "type": "board_patch",
            "run_id": run_id,
            "patch_id": patch_id,
            "ops": ops,
        }
    )
    if required and not sent:
        record(
            "board.patch_dropped",
            run_id,
            cfg=get_config(),
            patch_id=patch_id,
            reason="extension_not_connected",
        )
        raise ExtensionNotConnectedError("extension not connected — board patch not delivered")


async def _patch_work_item(
    item_id: str,
    *,
    status: str,
    run_id: str,
    evidence: dict[str, Any] | None = None,
    last_error: str | None = None,
) -> dict[str, Any] | None:
    item = _work_items.get(item_id)
    if not item:
        return None
    updated = {**item, "status": status, "run_id": run_id}
    if evidence:
        updated["evidence"] = {**(item.get("evidence") or {}), **evidence}
    if last_error is not None:
        updated["last_error"] = last_error
    _work_items[item_id] = updated
    patch_id = uuid.uuid4().hex
    await _send_board_patch(
        run_id,
        patch_id,
        [{"op": "update", "item": updated}],
        required=True,
    )
    return updated


async def _send_to_extension(message: dict[str, Any]) -> bool:
    if _extension_ws is None:
        return False
    await _extension_ws.send_json(message)
    return True


def reset_state_for_tests() -> None:
    """Clear in-memory hub state between tests."""
    global _extension_ws, _extension_connected
    _proposals.clear()
    _work_items.clear()
    _handoff_urls.clear()
    _handoff_meta.clear()
    _screenshot_counts.clear()
    _command_results.clear()
    for fut in list(_command_waiters.values()):
        if not fut.done():
            fut.cancel()
    _command_waiters.clear()
    for fut in list(_memory_waiters.values()):
        if not fut.done():
            fut.cancel()
    _memory_waiters.clear()
    _browser_result_counts.clear()
    _command_evidence_flags.clear()
    _execute_ops.clear()
    _command_ops.clear()
    _last_probe_links_empty.clear()
    _extension_ws = None
    _extension_connected = False
    harness_reset_for_tests()
    reset_config_cache()


@app.post("/v1/items/{item_id}/accept")
async def accept_item(item_id: str, body: AcceptBody) -> dict[str, Any]:
    """Commit a Waiting proposal. Tab provisioning for Waiting items is future work — see docs/NEXTSTEPS.md."""
    prop = _proposals.get(body.proposal_id)
    if not prop:
        raise HTTPException(status_code=404, detail="proposal not found")
    record(
        "proposal.accepted",
        body.run_id,
        cfg=get_config(),
        proposal_id=body.proposal_id,
        proposal_kind=prop.get("kind"),
    )
    committed: dict[str, Any] = {"kind": prop.get("kind")}
    if prop.get("kind") == "calendar_slot":
        committed.update(book_calendar_slot(prop.get("payload") or {}))
    try:
        _require_extension()
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await _patch_work_item(item_id, status="done", run_id=body.run_id)
    return {"ok": True, "work_item_id": item_id, "status": "done", "committed": committed}


def _browser_results_for_run(run_id: str) -> int:
    return _browser_result_counts.get(run_id, 0)


@app.post("/v1/browser")
async def browser_command(body: BrowserCommandBody) -> dict[str, Any]:
    """desk_browser tool entry — extension or harness driver for execute ops."""
    cmd = body.model_dump(exclude={"wait", "wait_timeout_sec"})
    if not cmd.get("handoff_url") and cmd.get("run_id"):
        cmd["handoff_url"] = _handoff_urls.get(cmd["run_id"], "")
    cmd = normalize_browser_command(cmd)
    if not cmd.get("command_id"):
        cmd["command_id"] = uuid.uuid4().hex
    cfg = get_config()
    harness_path = uses_harness_driver(cfg.browser.driver) and is_harness_op(
        str(cmd.get("op") or "")
    )
    try:
        if body.wait:
            if not harness_path:
                _require_extension()
            result = await dispatch_browser_command_and_wait(
                cmd, timeout=body.wait_timeout_sec
            )
            return {"ok": True, "command_id": cmd["command_id"], "result": result}
        if not harness_path:
            _require_extension()
        await dispatch_browser_command(cmd)
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HarnessBackendError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="command_result timeout") from exc
    return {"ok": True, "command_id": cmd["command_id"]}


async def _dispatch_harness_and_record(command: dict[str, Any]) -> dict[str, Any]:
    """Run harness op synchronously in a thread; record events like extension path."""
    cfg = get_config()
    run_id = command.get("run_id", "")
    cid = command.get("command_id") or ""
    op = command.get("op", "")

    def _run() -> dict[str, Any]:
        return harness_run_browser_op(
            command,
            harness_bin=cfg.browser.harness_bin,
            bu_name=cfg.browser.harness_bu_name,
            timeout_sec=float(cfg.host.browser_wait_timeout_sec),
            excerpt_max=int(cfg.browser.scrape_excerpt_max_chars),
            skip_screenshot=bool(command.get("skip_screenshot")),
        )

    try:
        result = await asyncio.to_thread(_run)
    except HarnessBackendError:
        raise

    _command_results[cid] = result
    fields = browser_command_result_fields(
        result,
        op=str(op) if op else None,
        screenshot_count_run_total=_screenshot_counts.get(run_id, 0),
    )
    flags = {**fields["flags"], "driver": "harness"}
    record(
        "browser.command_result",
        run_id,
        cfg=cfg,
        include_limits=False,
        measure=fields["measure"],
        flags=flags,
        driver="harness",
        **fields["detail"],
    )
    if run_id and result.get("ok"):
        count_evidence = _command_evidence_flags.pop(cid, True)
        if count_evidence:
            _browser_result_counts[run_id] = _browser_result_counts.get(run_id, 0) + 1
        if op == "probe_links":
            links = result.get("links") or []
            _last_probe_links_empty[run_id] = len(links) == 0
    if cfg.observability.persist_screenshots and result.get("screenshot"):
        path = persist_screenshot(run_id, cid, result["screenshot"])
        if path:
            result["screenshot_ref"] = path
    return result


async def dispatch_browser_command(command: dict[str, Any]) -> None:
    command = normalize_browser_command(command)
    run_id = command.get("run_id", "")
    op = command.get("op", "")
    cfg = get_config()
    cid = command.get("command_id")
    if cid:
        _command_evidence_flags[cid] = command.get("count_evidence", True)
        _command_ops[cid] = str(op)
    if run_id and op:
        _execute_ops.setdefault(str(run_id), []).append(str(op))

    harness_path = uses_harness_driver(cfg.browser.driver) and is_harness_op(str(op))

    # Path B: execute observe skips captureVisibleTab unless caller overrides False.
    if (
        op == "observe"
        and not harness_path
        and cfg.browser.observe_skip_screenshot_default
        and command.get("skip_screenshot") is None
    ):
        command["skip_screenshot"] = True

    if op in SCREENSHOT_OPS and run_id:
        count = _screenshot_counts.get(run_id, 0)
        if count >= cfg.browser.screenshot_max_per_run:
            command["skip_screenshot"] = True
            record(
                "policy.screenshot_skipped",
                run_id,
                cfg=cfg,
                measure={"count": count},
                rule="screenshot_cap",
                op=op,
            )
        else:
            _screenshot_counts[run_id] = count + 1

    reason = policy_denied_reason(
        command.get("op", ""),
        command.get("tab_id"),
        command.get("human_tab_id"),
    )
    if reason:
        record(
            "policy.denied",
            command.get("run_id", ""),
            cfg=cfg,
            rule=reason,
            op=command.get("op"),
        )
        raise PermissionError(reason)

    if op == "closeTab" and command.get("tab_id") is None:
        result = {
            "command_id": cid,
            "ok": False,
            "error": "closeTab requires tab_id",
            "duration_ms": 0,
            "op": "closeTab",
        }
        if cid:
            _command_results[cid] = result
            _command_ops.pop(cid, None)
            _command_evidence_flags.pop(cid, None)
        fields = browser_command_result_fields(result, op="closeTab")
        record(
            "browser.command_result",
            run_id,
            cfg=cfg,
            include_limits=False,
            measure=fields["measure"],
            flags=fields["flags"],
            **fields["detail"],
        )
        waiter = _command_waiters.get(cid or "")
        if waiter and not waiter.done():
            waiter.set_result(result)
        return

    driver = "harness" if harness_path else "extension"
    record(
        "browser.command",
        command.get("run_id", ""),
        cfg=cfg,
        include_limits=False,
        command_id=command.get("command_id"),
        op=command.get("op"),
        driver=driver,
    )

    if harness_path:
        # Fire-and-forget style: run and stash result for waiters if any.
        result = await _dispatch_harness_and_record(command)
        waiter = _command_waiters.get(cid or "")
        if waiter and not waiter.done():
            waiter.set_result(result)
        return

    sent = await _send_to_extension({"type": "browser_command", "command": command})
    if not sent:
        raise ExtensionNotConnectedError("extension not connected")


async def dispatch_browser_command_and_wait(
    command: dict[str, Any],
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    cid = command.get("command_id") or uuid.uuid4().hex
    command["command_id"] = cid
    cfg = get_config()
    harness_path = uses_harness_driver(cfg.browser.driver) and is_harness_op(
        str(command.get("op") or "")
    )
    if harness_path:
        # Apply the same pre-flight as dispatch (caps + policy + record command).
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        _command_waiters[cid] = fut
        try:
            await dispatch_browser_command(command)
            if fut.done():
                return fut.result()
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            _command_waiters.pop(cid, None)

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _command_waiters[cid] = fut
    try:
        await dispatch_browser_command(command)
        return await asyncio.wait_for(fut, timeout=timeout)
    finally:
        _command_waiters.pop(cid, None)


@app.post("/v1/items/{item_id}/deny")
async def deny_item(item_id: str, body: DenyBody) -> dict[str, Any]:
    record(
        "proposal.denied",
        body.run_id,
        cfg=get_config(),
        proposal_id=body.proposal_id,
        reason=body.reason,
    )
    try:
        _require_extension()
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await _patch_work_item(item_id, status="denied", run_id=body.run_id)
    return {"ok": True, "work_item_id": item_id, "status": "denied"}


@app.patch("/v1/items/{item_id}")
async def patch_item_meta(item_id: str, body: ItemMetaBody) -> dict[str, Any]:
    """Extension sets per-item agent_tab_id after provisioning duplicate tabs."""
    item = _work_items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="work item not found")
    updated = {**item, "agent_tab_id": body.agent_tab_id, "run_id": body.run_id}
    _work_items[item_id] = updated
    patch_id = uuid.uuid4().hex
    await _send_board_patch(
        body.run_id,
        patch_id,
        [{"op": "update", "item": updated}],
    )
    record(
        "item.agent_tab_assigned",
        body.run_id,
        cfg=get_config(),
        item_id=item_id,
        agent_tab_id=body.agent_tab_id,
    )
    return {"ok": True, "item": updated}


@app.post("/v1/items/mint")
async def mint_item(body: MintItemBody) -> dict[str, Any]:
    """Mid-flight subtask mint — Hermes via desk-browser --op mint_item."""
    if body.column not in ("you", "agent", "waiting"):
        raise HTTPException(status_code=400, detail="column must be you|agent|waiting")
    parent = _work_items.get(body.parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="parent work item not found")
    if parent.get("run_id") and parent.get("run_id") != body.run_id:
        raise HTTPException(status_code=400, detail="parent run_id mismatch")
    try:
        _require_extension()
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    short = uuid.uuid4().hex[:8]
    item_id = f"{body.parent_id}_sub_{short}"
    source = body.source or dict(parent.get("source") or {"kind": "handoff"})
    if body.source and body.source.get("url"):
        source = {**source, "url": body.source["url"]}
    item: dict[str, Any] = {
        "id": item_id,
        "column": body.column,
        "title": body.title[:200],
        "status": body.status if body.status in ("proposed", "running") else "proposed",
        "kind": "subtask",
        "parent_id": body.parent_id,
        "source": source,
        "run_id": body.run_id,
        "human_tab_id": parent.get("human_tab_id"),
        "proposals": [],
    }
    if body.hints:
        item["hints"] = body.hints
    # Agent subtasks share the parent's agent tab when present (no new collage).
    if body.column == "agent" and parent.get("agent_tab_id") is not None:
        item["agent_tab_id"] = parent["agent_tab_id"]

    _work_items[item_id] = item
    patch_id = uuid.uuid4().hex
    try:
        await _send_board_patch(
            body.run_id,
            patch_id,
            [{"op": "add", "item": item}],
            required=True,
        )
    except ExtensionNotConnectedError as exc:
        _work_items.pop(item_id, None)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record(
        "item.minted",
        body.run_id,
        cfg=get_config(),
        item_id=item_id,
        parent_id=body.parent_id,
        column=body.column,
    )
    return {"ok": True, "item": item}


@app.post("/v1/items/{item_id}/execute")
async def execute_item(item_id: str, body: ExecuteBody) -> dict[str, Any]:
    item = _work_items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="work item not found")
    if item.get("column") != "agent":
        raise HTTPException(status_code=400, detail="execute only for agent column")
    try:
        _require_extension()
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    meta = _handoff_meta.get(body.run_id, {})
    ctx = {
        "run_id": body.run_id,
        # Prefer per-item tab from Run-agent provision; do not fall back to a
        # closed handoff snapshot id stored on meta.
        "agent_tab_id": item.get("agent_tab_id"),
        "human_tab_id": item.get("human_tab_id") or meta.get("human_tab_id"),
        "handoff_url": _handoff_urls.get(body.run_id, ""),
    }
    memory = await _memory_get(body.run_id)
    ctx.update(
        format_for_execute(
            memory,
            body.run_id,
            decomposition=str(meta.get("decomposition") or ""),
        )
    )
    backend = get_backend()
    execute_fn = getattr(backend, "execute_item", None)
    if not execute_fn:
        raise HTTPException(status_code=501, detail="backend does not support execute")
    cfg = get_config()
    browser_before = _browser_results_for_run(body.run_id)
    _execute_ops[body.run_id] = []
    _last_probe_links_empty[body.run_id] = False
    await _execute_session_start(
        run_id=body.run_id,
        item_id=item_id,
        agent_tab_id=ctx.get("agent_tab_id"),
        human_tab_id=ctx.get("human_tab_id"),
        handoff_url=str(ctx.get("handoff_url") or ""),
    )
    record("agent.execute_started", body.run_id, cfg=cfg, item_id=item_id)
    http_exc: HTTPException | None = None
    preserve_tabs = False
    try:
        try:
            result = await execute_fn(item, ctx)
        except Exception as exc:
            err = str(exc)[: cfg.prompts.event_snippet_max_chars]
            record(
                "agent.execute_failed",
                body.run_id,
                cfg=cfg,
                item_id=item_id,
                error=err,
            )
            try:
                await _patch_work_item(
                    item_id,
                    status="failed",
                    run_id=body.run_id,
                    last_error=err,
                )
            except ExtensionNotConnectedError:
                pass
            await _record_execute_memory(
                run_id=body.run_id,
                item=item,
                outcome="failed",
                summary=err,
            )
            http_exc = HTTPException(status_code=500, detail=err)
            raise http_exc from exc
        browser_after = _browser_results_for_run(body.run_id)
        if cfg.hermes.execute_require_browser_evidence and browser_after <= browser_before:
            err = "execute completed without browser evidence"
            record(
                "agent.execute_failed",
                body.run_id,
                cfg=cfg,
                item_id=item_id,
                error=err,
            )
            await _patch_work_item(
                item_id,
                status="failed",
                run_id=body.run_id,
                last_error=err,
            )
            await _record_execute_memory(
                run_id=body.run_id,
                item=item,
                outcome="failed",
                summary=err,
            )
            http_exc = HTTPException(status_code=422, detail=err)
            raise http_exc
        evidence = {
            "summary": (result or {}).get("summary", ""),
            "browser_ops": browser_after - browser_before,
        }
        incomplete = execute_summary_incomplete_reason(str(evidence["summary"] or ""))
        if not incomplete:
            incomplete = empty_probe_links_only_cover(
                ops_since_start=list(_execute_ops.get(body.run_id, [])),
                last_probe_links_empty=bool(
                    _last_probe_links_empty.get(body.run_id, False)
                ),
            )
        if incomplete:
            err = incomplete if incomplete.lower().startswith("partial:") else f"Partial: {incomplete}"
            record(
                "agent.execute_failed",
                body.run_id,
                cfg=cfg,
                item_id=item_id,
                error=err,
            )
            await _patch_work_item(
                item_id,
                status="failed",
                run_id=body.run_id,
                evidence=evidence,
                last_error=err,
            )
            await _record_execute_memory(
                run_id=body.run_id,
                item=item,
                outcome="failed",
                summary=err,
            )
            http_exc = HTTPException(status_code=422, detail=err)
            raise http_exc
        # Re-read item in case mint_item updated the board mid-flight.
        current = _work_items.get(item_id) or item
        blocked = parent_done_blocked_reason(current, _work_items)
        if blocked:
            preserve_tabs = True
            await _patch_work_item(
                item_id,
                status="running",
                run_id=body.run_id,
                evidence=evidence,
                last_error=blocked,
            )
            await _record_execute_memory(
                run_id=body.run_id,
                item=current,
                outcome="running",
                summary=f"{evidence['summary']} ({blocked})",
            )
            record(
                "agent.execute_blocked_children",
                body.run_id,
                cfg=cfg,
                item_id=item_id,
                error=blocked,
            )
            return {
                "ok": False,
                "work_item_id": item_id,
                "status": "running",
                "blocked": blocked,
                "result": result,
            }
        await _patch_work_item(
            item_id,
            status="done",
            run_id=body.run_id,
            evidence=evidence,
        )
        await _record_execute_memory(
            run_id=body.run_id,
            item=item,
            outcome="done",
            summary=str(evidence["summary"] or ""),
        )
        record(
            "agent.executed",
            body.run_id,
            cfg=cfg,
            measure={
                "browser_ops": evidence["browser_ops"],
                "exit_code": (result or {}).get("exit_code"),
            },
            item_id=item_id,
            summary_snippet=evidence["summary"][: cfg.prompts.event_summary_snippet_max_chars],
        )
        record(
            "run.finished",
            body.run_id,
            cfg=cfg,
            backend=os.environ.get("DESK_AGENT_BACKEND", "mock"),
            item_id=item_id,
        )
        return {"ok": True, "work_item_id": item_id, "status": "done", "result": result}
    finally:
        await _execute_cleanup(
            run_id=body.run_id,
            item_id=item_id,
            agent_tab_id=ctx.get("agent_tab_id"),
            human_tab_id=ctx.get("human_tab_id"),
            preserve_tabs=preserve_tabs,
        )



@app.post("/v1/items/{item_id}/complete")
async def complete_item(item_id: str, body: CompleteBody) -> dict[str, Any]:
    item = _work_items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="work item not found")
    if item.get("column") != "you":
        raise HTTPException(status_code=400, detail="complete only for you column")
    try:
        _require_extension()
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await _patch_work_item(item_id, status="done", run_id=body.run_id)
    record("item.completed", body.run_id, cfg=get_config(), item_id=item_id, column="you")
    return {"ok": True, "work_item_id": item_id, "status": "done"}


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
            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})
            elif msg_type == "handoff_started":
                handoff = raw.get("handoff") or {}
                result = await _handle_handoff(handoff)
                await ws.send_json({"type": "handoff_result", **result})
            elif msg_type == "memory_snapshot":
                request_id = raw.get("request_id") or ""
                waiter = _memory_waiters.pop(request_id, None)
                if waiter and not waiter.done():
                    waiter.set_result(raw)
            elif msg_type == "browser_popup_closed":
                record(
                    "browser.popup_closed",
                    raw.get("run_id", ""),
                    cfg=get_config(),
                    item_id=raw.get("item_id"),
                    tab_id=raw.get("tab_id"),
                    url=raw.get("url"),
                )
            elif msg_type == "execute_cleanup_done":
                record(
                    "execute.cleanup_done",
                    raw.get("run_id", ""),
                    cfg=get_config(),
                    include_limits=False,
                    item_id=raw.get("item_id"),
                    closed_tab_ids=raw.get("closed_tab_ids") or [],
                    measure={
                        "closed_tab_count": len(raw.get("closed_tab_ids") or []),
                    },
                )
            elif msg_type == "command_result":
                result = raw.get("result") or {}
                cid = result.get("command_id")
                if cid:
                    _command_results[cid] = result
                    waiter = _command_waiters.pop(cid, None)
                    if waiter and not waiter.done():
                        waiter.set_result(result)
                run_id = raw.get("run_id", "")
                cfg = get_config()
                op_name = _command_ops.get(cid or "", "") or result.get("op")
                fields = browser_command_result_fields(
                    result,
                    op=str(op_name) if op_name else None,
                    screenshot_count_run_total=_screenshot_counts.get(run_id, 0),
                )
                record(
                    "browser.command_result",
                    run_id,
                    cfg=cfg,
                    include_limits=False,
                    measure=fields["measure"],
                    flags=fields["flags"],
                    **fields["detail"],
                )
                if run_id and result.get("ok"):
                    count_evidence = _command_evidence_flags.pop(cid or "", True)
                    if count_evidence:
                        _browser_result_counts[run_id] = (
                            _browser_result_counts.get(run_id, 0) + 1
                        )
                    op_popped = _command_ops.pop(cid or "", "")
                    if op_popped == "probe_links":
                        links = result.get("links") or []
                        _last_probe_links_empty[run_id] = len(links) == 0
                elif cid:
                    _command_ops.pop(cid or "", None)
                    _command_evidence_flags.pop(cid or "", None)
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
