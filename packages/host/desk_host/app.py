"""FastAPI application and WebSocket hub."""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager, suppress
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
from .memory import empty_memory, empty_semantic, format_for_execute
from .navigation import normalize_browser_command
from .observability import (
    browser_command_result_fields,
    measure_from_snapshot,
    record,
    site_fingerprint,
    usage_measure,
)
from .backends.hermes import HermesExecuteError
from .execute_errors import HostExecuteError
from .policy import policy_denied_reason
from .execute_validation import (
    auth_gate_blocks_false_closure,
    empty_probe_links_only_cover,
    execute_summary_incomplete_reason,
    failed_open_tab_blocks_done,
    human_judgment_blocks_false_closure,
    open_auth_gate_you,
    open_you_remainder,
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
_executing_item_ids: set[str] = set()
_executing_run_ids: dict[str, str] = {}  # run_id -> item_id or "__run_tab__"
_run_abort_flags: dict[str, bool] = {}
_command_evidence_flags: dict[str, bool] = {}
_execute_ops: dict[str, list[str]] = {}
_failed_ops: dict[str, list[str]] = {}
_command_ops: dict[str, str] = {}
_last_probe_links_empty: dict[str, bool] = {}
# Execute-scoped obs: stamp browser.* with item_id / op_seq for procedure mining.
_active_item_by_run: dict[str, str] = {}
_op_seq_by_key: dict[tuple[str, str], int] = {}
_pending_command_meta: dict[str, dict[str, Any]] = {}

SCREENSHOT_OPS = frozenset(
    {"click", "fill", "upload", "scroll", "scrape", "screenshot", "openTab", "duplicateTab"}
)


class ExtensionNotConnectedError(Exception):
    """Raised when the Chrome extension WebSocket is not connected."""


def _require_extension() -> None:
    if not _extension_connected or _extension_ws is None:
        raise ExtensionNotConnectedError("extension not connected")

def _binding_hints_from_command(command: dict[str, Any]) -> dict[str, Any]:
    """Small mineable params for procedure reconciliation (not full Packet)."""
    hints: dict[str, Any] = {}
    if command.get("tab_id") is not None:
        hints["tab_id"] = command.get("tab_id")
    if command.get("url"):
        hints["url"] = str(command.get("url"))[:500]
    params = command.get("params")
    if isinstance(params, dict):
        for key in ("target_id", "ref", "text", "contains", "selector", "frame_id"):
            if params.get(key) is None:
                continue
            val = params.get(key)
            if isinstance(val, str):
                hints[key] = val[:200]
            else:
                hints[key] = val
        if params.get("url") and "url" not in hints:
            hints["url"] = str(params.get("url"))[:500]
    return hints


def _next_op_seq(run_id: str, item_id: str) -> int:
    key = (run_id, item_id)
    n = _op_seq_by_key.get(key, 0) + 1
    _op_seq_by_key[key] = n
    return n


def _execute_obs_context(run_id: str, command: dict[str, Any] | None = None) -> dict[str, Any]:
    item_id = None
    if command and command.get("item_id"):
        item_id = str(command.get("item_id"))
    if not item_id:
        item_id = _active_item_by_run.get(run_id)
    out: dict[str, Any] = {}
    if item_id:
        out["item_id"] = item_id
    return out


def _obs_from_pending_command(
    cid: str | None,
    *,
    run_id: str = "",
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pull item_id/op_seq from pending command meta; fingerprint from result URL."""
    extra: dict[str, Any] = {}
    meta = _pending_command_meta.pop(str(cid), None) if cid else None
    if isinstance(meta, dict):
        if meta.get("item_id"):
            extra["item_id"] = meta["item_id"]
        if meta.get("op_seq") is not None:
            extra["op_seq"] = meta["op_seq"]
    if not extra.get("item_id") and run_id:
        mapped = _active_item_by_run.get(run_id)
        if mapped:
            extra["item_id"] = mapped
    url = None
    if result:
        url = result.get("url")
    if url:
        fp = site_fingerprint(str(url))
        if fp:
            extra["site_fingerprint"] = fp
    return extra


def _record_execute_failed_event(
    *,
    run_id: str,
    item_id: str,
    err: str,
    exc: Exception | None = None,
    measure: dict[str, Any] | None = None,
    outcome: str = "failed",
) -> None:
    cfg = get_config()
    cap = cfg.prompts.event_snippet_max_chars
    fields: dict[str, Any] = {
        "item_id": item_id,
        "error": err[:cap],
        "flags": {"outcome": outcome},
    }
    merged_measure: dict[str, Any] = dict(measure or {})
    if isinstance(exc, (HermesExecuteError, HostExecuteError)):
        if getattr(exc, "exit_code", None) is not None:
            merged_measure["exit_code"] = exc.exit_code
        usage = usage_measure(getattr(exc, "usage", None) or {})
        if usage:
            merged_measure.update(usage)
        if getattr(exc, "empty_output", False):
            fields["flags"]["empty_output"] = True
            fields["flags"]["outcome"] = "empty_output"
        stdout = getattr(exc, "stdout", "") or ""
        stderr = getattr(exc, "stderr", "") or ""
        if stdout:
            fields["stdout_snippet"] = stdout[:cap]
        if stderr:
            fields["stderr_snippet"] = stderr[:cap]
    if merged_measure:
        fields["measure"] = merged_measure
    record("agent.execute_failed", run_id, cfg=cfg, **fields)


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


class ExecuteRunBody(BaseModel):
    """Optional agent_tab_id when extension already provisioned one shared tab."""

    agent_tab_id: int | None = None
    human_tab_id: int | None = None


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
    park_kind: str | None = None
    resume: bool | None = None


class CompleteBody(BaseModel):
    run_id: str
    viewport_shot: dict[str, Any] | None = None
    shot_on_agent_tab: bool | None = None


class TabCustodyBody(BaseModel):
    run_id: str
    action: str  # park | reveal
    agent_tab_id: int | None = None
    viewport_shot: dict[str, Any] | None = None
    flags: dict[str, Any] | None = None


class SemanticMemoryBody(BaseModel):
    op: str
    key: str | None = None
    value: str | None = None
    tags: list[str] | None = None
    id: str | None = None
    fact_id: str | None = None
    source: str | None = None


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


@app.get("/v1/desk-memory/semantic")
async def get_semantic_memory() -> dict[str, Any]:
    _require_extension()
    snap = await _memory_get("")
    return {"semantic": snap["semantic"]}


@app.patch("/v1/desk-memory/semantic")
async def patch_semantic_memory(body: SemanticMemoryBody) -> dict[str, Any]:
    _require_extension()
    op = (body.op or "").strip()
    if op not in ("upsert_fact", "delete_fact"):
        raise HTTPException(
            status_code=400,
            detail="op must be upsert_fact or delete_fact",
        )
    patch_op: dict[str, Any] = {"op": op}
    if body.key is not None:
        patch_op["key"] = body.key
    if body.value is not None:
        patch_op["value"] = body.value
    if body.tags is not None:
        patch_op["tags"] = body.tags
    if body.id is not None:
        patch_op["id"] = body.id
    if body.fact_id is not None:
        patch_op["fact_id"] = body.fact_id
    patch_op["source"] = body.source or "host"
    if op == "upsert_fact" and (not body.key or not body.value):
        raise HTTPException(status_code=400, detail="upsert_fact requires key and value")
    if op == "delete_fact" and not body.key and not body.id and not body.fact_id:
        raise HTTPException(status_code=400, detail="delete_fact requires key or id")
    sent = await _memory_patch([patch_op])
    if not sent:
        raise HTTPException(status_code=503, detail="extension not connected")
    # Brief yield so extension can apply before optional follow-up GET.
    await asyncio.sleep(0)
    snap = await _memory_get("")
    semantic = snap["semantic"]
    fact_count = len((semantic or {}).get("facts") or [])
    record(
        "memory.semantic_patched",
        "",
        cfg=get_config(),
        measure={"semantic_fact_count": fact_count},
        flags={"upsert": op == "upsert_fact", "delete": op == "delete_fact"},
        op=op,
        key=body.key,
    )
    return {"ok": True, "semantic": semantic}


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
    record(
        "handoff.started",
        run_id,
        cfg=cfg,
        url=payload.get("url"),
        intent=(str(payload.get("intent") or "").strip() or None),
    )
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
    decomposition = str(result.get("decomposition") or "")
    items = list(result.get("items") or [])
    item_titles = [
        str(it.get("title") or "").strip()
        for it in items
        if str(it.get("title") or "").strip()
    ]
    record(
        "handoff.decomposed",
        run_id,
        cfg=cfg,
        measure={
            "item_count": len(items),
            **usage_measure(result.get("usage")),
        },
        flags=decompose_flags,
        backend=os.environ.get("DESK_AGENT_BACKEND", "mock"),
        item_titles=item_titles[: cfg.prompts.decompose_items_max],
        decomposition_snippet=decomposition[: cfg.prompts.event_summary_snippet_max_chars],
    )
    _handoff_meta[run_id]["decomposition"] = decomposition
    patch_id = uuid.uuid4().hex
    ops: list[dict[str, Any]] = [{"op": "clear"}]
    ops.extend({"op": "add", "item": item} for item in items)
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
    for item in items:
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
    """Ask extension for memory + semantic snapshot; empty defaults on failure."""
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
            return {"memory": empty_memory(), "semantic": empty_semantic(), "vault": {"files": []}}
        snap = await asyncio.wait_for(fut, timeout=timeout)
        return {
            "memory": snap.get("memory") or empty_memory(),
            "semantic": snap.get("semantic") or empty_semantic(),
            "vault": snap.get("vault")
            if isinstance(snap.get("vault"), dict)
            else {"files": []},
        }
    except (asyncio.TimeoutError, ExtensionNotConnectedError):
        return {"memory": empty_memory(), "semantic": empty_semantic(), "vault": {"files": []}}
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
    _active_item_by_run[run_id] = item_id
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


def _execute_session_end(run_id: str, item_id: str | None = None) -> None:
    """Clear active-item obs for this execute; only drop map entry if it still matches."""
    if item_id:
        _op_seq_by_key.pop((run_id, item_id), None)
        if _active_item_by_run.get(run_id) == item_id:
            _active_item_by_run.pop(run_id, None)
        return
    popped = _active_item_by_run.pop(run_id, None)
    if popped:
        _op_seq_by_key.pop((run_id, popped), None)


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
    column: str | None = None,
    evidence: dict[str, Any] | None = None,
    last_error: str | None = None,
    clear_last_error: bool = False,
) -> dict[str, Any] | None:
    item = _work_items.get(item_id)
    if not item:
        return None
    updated = {**item, "status": status, "run_id": run_id}
    if column:
        updated["column"] = column
    if evidence:
        updated["evidence"] = {**(item.get("evidence") or {}), **evidence}
    if last_error is not None:
        updated["last_error"] = last_error
    elif clear_last_error:
        updated.pop("last_error", None)
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
    _failed_ops.clear()
    _command_ops.clear()
    _last_probe_links_empty.clear()
    _executing_item_ids.clear()
    _executing_run_ids.clear()
    _active_item_by_run.clear()
    _op_seq_by_key.clear()
    _pending_command_meta.clear()
    _extension_ws = None
    _extension_connected = False
    harness_reset_for_tests()
    reset_config_cache()


@app.post("/v1/items/{item_id}/accept")
async def accept_item(item_id: str, body: AcceptBody) -> dict[str, Any]:
    """Commit a Waiting proposal. Non-calendar kinds move to Agent + request tab provision."""
    prop = _proposals.get(body.proposal_id)
    if not prop:
        raise HTTPException(status_code=404, detail="proposal not found")
    kind = str(prop.get("kind") or "")
    # Calendar stub commits without browser; other proposal kinds need an agent tab for UI work.
    calendar_only = kind in ("calendar_slot", "")
    needs_agent_tab = not calendar_only
    record(
        "proposal.accepted",
        body.run_id,
        cfg=get_config(),
        proposal_id=body.proposal_id,
        proposal_kind=prop.get("kind"),
        needs_agent_tab=needs_agent_tab,
    )
    committed: dict[str, Any] = {"kind": prop.get("kind")}
    if kind == "calendar_slot":
        committed.update(book_calendar_slot(prop.get("payload") or {}))
    try:
        _require_extension()
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if calendar_only:
        await _patch_work_item(item_id, status="done", run_id=body.run_id)
        status = "done"
    else:
        # Agent column so Run agent / Run tab can execute after extension stamps agent_tab_id.
        await _patch_work_item(
            item_id,
            status="proposed",
            run_id=body.run_id,
            column="agent",
        )
        status = "proposed"
    live = _work_items.get(item_id) or {}
    return {
        "ok": True,
        "work_item_id": item_id,
        "status": status,
        "column": live.get("column"),
        "committed": committed,
        "needs_agent_tab": needs_agent_tab,
    }


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
    extra = _obs_from_pending_command(cid, run_id=str(run_id or ""), result=result)
    record(
        "browser.command_result",
        run_id,
        cfg=cfg,
        include_limits=False,
        measure=fields["measure"],
        flags=flags,
        driver="harness",
        **fields["detail"],
        **extra,
    )
    if run_id and result.get("ok"):
        count_evidence = _command_evidence_flags.pop(cid, True)
        if count_evidence:
            _browser_result_counts[run_id] = _browser_result_counts.get(run_id, 0) + 1
        if op == "probe_links":
            links = result.get("links") or []
            _last_probe_links_empty[run_id] = len(links) == 0
    elif run_id and not result.get("ok"):
        failed_op = str(op or result.get("op") or "")
        if failed_op:
            _failed_ops.setdefault(run_id, []).append(failed_op)
        if cid:
            _command_evidence_flags.pop(cid, None)
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

    # Extension: execute observe skips captureVisibleTab unless caller overrides False.
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
        text=str(command.get("text") or ""),
        params=command.get("params") if isinstance(command.get("params"), dict) else None,
        url=command.get("url") if isinstance(command.get("url"), str) else None,
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
        if run_id:
            _failed_ops.setdefault(run_id, []).append("closeTab")
        fields = browser_command_result_fields(result, op="closeTab")
        extra = _obs_from_pending_command(cid, run_id=str(run_id or ""), result=result)
        record(
            "browser.command_result",
            run_id,
            cfg=cfg,
            include_limits=False,
            measure=fields["measure"],
            flags=fields["flags"],
            **fields["detail"],
            **extra,
        )
        waiter = _command_waiters.get(cid or "")
        if waiter and not waiter.done():
            waiter.set_result(result)
        return

    driver = "harness" if harness_path else "extension"
    run_id = str(command.get("run_id") or "")
    obs_ctx = _execute_obs_context(run_id, command)
    item_id = obs_ctx.get("item_id") or ""
    op_seq = _next_op_seq(run_id, item_id) if run_id else None
    hints = _binding_hints_from_command(command)
    cid = command.get("command_id")
    if cid:
        meta = {"item_id": item_id or None, "op_seq": op_seq}
        meta.update(hints)
        _pending_command_meta[str(cid)] = meta
    cmd_fields: dict[str, Any] = {
        "command_id": cid,
        "op": command.get("op"),
        "driver": driver,
    }
    if item_id:
        cmd_fields["item_id"] = item_id
    if op_seq is not None:
        cmd_fields["op_seq"] = op_seq
    cmd_fields.update(hints)
    record(
        "browser.command",
        run_id,
        cfg=cfg,
        include_limits=False,
        **cmd_fields,
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
    # Two-lane board: legacy waiting → you (Accept/Deny live on You proposals).
    mint_column = "you" if body.column == "waiting" else body.column
    parent = _work_items.get(body.parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="parent work item not found")
    if parent.get("run_id") and parent.get("run_id") != body.run_id:
        raise HTTPException(status_code=400, detail="parent run_id mismatch")
    try:
        _require_extension()
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    park_kind = body.park_kind if body.park_kind in ("auth_gate", "human_remainder") else None
    resume = bool(body.resume) if body.resume is not None else park_kind == "auth_gate"

    source = body.source or dict(parent.get("source") or {"kind": "handoff"})
    if body.source and body.source.get("url"):
        source = {**source, "url": body.source["url"]}
    source_url = (source or {}).get("url") if isinstance(source, dict) else None

    if mint_column == "you" and park_kind in ("auth_gate", "human_remainder") and not source_url:
        raise HTTPException(
            status_code=400,
            detail="You park with park_kind requires source.url",
        )

    short = uuid.uuid4().hex[:8]
    item_id = f"{body.parent_id}_sub_{short}"
    item: dict[str, Any] = {
        "id": item_id,
        "column": mint_column,
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
    if park_kind:
        item["park_kind"] = park_kind
    if resume:
        item["resume"] = True
    # Agent subtasks share the parent's agent tab when present (no new collage).
    # auth_gate You parks also get agent_tab_id so the panel can Show that tab.
    if parent.get("agent_tab_id") is not None and (
        mint_column == "agent" or park_kind == "auth_gate"
    ):
        item["agent_tab_id"] = parent["agent_tab_id"]

    _work_items[item_id] = item
    patch_ops: list[dict[str, Any]] = [{"op": "add", "item": item}]
    if mint_column == "you" and park_kind == "auth_gate":
        parent_updated = {
            **parent,
            "status": "awaiting_human",
            "run_id": body.run_id,
        }
        parent_updated.pop("last_error", None)
        _work_items[body.parent_id] = parent_updated
        patch_ops.append({"op": "update", "item": parent_updated})

    patch_id = uuid.uuid4().hex
    try:
        await _send_board_patch(
            body.run_id,
            patch_id,
            patch_ops,
            required=True,
        )
    except ExtensionNotConnectedError as exc:
        _work_items.pop(item_id, None)
        if mint_column == "you" and park_kind == "auth_gate":
            _work_items[body.parent_id] = parent
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record(
        "item.minted",
        body.run_id,
        cfg=get_config(),
        item_id=item_id,
        parent_id=body.parent_id,
        column=mint_column,
        flags={"park_kind": park_kind, "resume": resume} if park_kind else None,
    )
    return {"ok": True, "item": item}


def _agent_roots_for_run_tab(run_id: str) -> list[dict[str, Any]]:
    """Proposed/failed/resume-ready Agent roots eligible for Run tab."""
    out: list[dict[str, Any]] = []
    for item in _work_items.values():
        if item.get("run_id") != run_id:
            continue
        if item.get("column") != "agent":
            continue
        if item.get("parent_id"):
            continue
        st = item.get("status")
        if st in ("proposed", "failed") or item.get("resume_ready"):
            out.append(item)
        elif st == "awaiting_human" and item.get("resume_ready"):
            out.append(item)
    # Stable order by id for A/B reproducibility.
    out.sort(key=lambda i: str(i.get("id") or ""))
    return out


@app.post("/v1/runs/{run_id}/execute")
async def execute_run(run_id: str, body: ExecuteRunBody = ExecuteRunBody()) -> dict[str, Any]:
    """Run tab: one host_loop over all eligible Agent roots (host_loop only)."""
    cfg = get_config()
    use_host_loop = str(cfg.execute.runtime or "").strip().lower() == "host_loop"
    if not use_host_loop:
        raise HTTPException(
            status_code=501,
            detail="Run tab requires execute.runtime=host_loop",
        )
    if run_id in _executing_run_ids:
        other = _executing_run_ids[run_id]
        raise HTTPException(
            status_code=409,
            detail=f"execute already in progress for this run ({other})",
        )
    try:
        _require_extension()
    except ExtensionNotConnectedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    items = _agent_roots_for_run_tab(run_id)
    if not items:
        raise HTTPException(status_code=400, detail="no proposed Agent items for this run")

    meta = _handoff_meta.get(run_id, {})
    human_tab = body.human_tab_id or meta.get("human_tab_id") or items[0].get("human_tab_id")
    agent_tab = body.agent_tab_id
    if agent_tab is None:
        for it in items:
            if it.get("agent_tab_id") is not None:
                agent_tab = it.get("agent_tab_id")
                break
    if human_tab is None or agent_tab is None:
        raise HTTPException(
            status_code=400,
            detail="missing human_tab_id or agent_tab_id — provision agent tab before Run tab",
        )

    # Stamp shared agent tab onto all items in this run.
    for it in items:
        iid = str(it["id"])
        updated = {**it, "agent_tab_id": agent_tab, "human_tab_id": human_tab}
        _work_items[iid] = updated
        try:
            await _patch_work_item(iid, status="running", run_id=run_id, clear_last_error=True)
        except ExtensionNotConnectedError:
            _work_items[iid] = {**updated, "status": "running"}

    items = [_work_items[str(i["id"])] for i in items]

    ctx: dict[str, Any] = {
        "run_id": run_id,
        "agent_tab_id": agent_tab,
        "human_tab_id": human_tab,
        "handoff_url": _handoff_urls.get(run_id, ""),
    }
    snap = await _memory_get(run_id)
    memory_slice = format_for_execute(
        snap["memory"],
        run_id,
        decomposition=str(meta.get("decomposition") or ""),
        semantic=snap["semantic"],
        packet_max_facts=cfg.memory.semantic_packet_max_facts,
        max_key_chars=cfg.memory.semantic_max_key_chars,
        max_value_chars=cfg.memory.semantic_max_value_chars,
    )
    ctx.update(memory_slice)
    vault = snap.get("vault") if isinstance(snap.get("vault"), dict) else {"files": []}
    ctx["vault"] = {
        "files": list(vault.get("files") or [])[:20],
        "note": (
            "Operator-supplied files. Use upload(vault_id, target_id) for kind:file Eyes. "
            "If vault is empty and a site needs an attachment, park You (human_remainder)."
        ),
    }

    # Collect cleared_gates from any resume-ready item.
    cleared: list[Any] = []
    for it in items:
        if it.get("resume_ready") or it.get("cleared_gates"):
            cleared.extend(list(it.get("cleared_gates") or []))
            if it.get("resume_ready"):
                cleared_item = {**it, "resume_ready": False}
                _work_items[str(it["id"])] = cleared_item
    if cleared:
        ctx["resume"] = {
            "ready": True,
            "cleared_gates": cleared,
            "note": (
                "Human cleared these gate URLs. Do not mint another You card for them; "
                "continue agent work past the gate."
            ),
        }

    browser_before = _browser_results_for_run(run_id)
    _execute_ops[run_id] = []
    _failed_ops[run_id] = []
    _last_probe_links_empty[run_id] = False
    _run_abort_flags[run_id] = False
    preserve_tabs = False
    http_exc: HTTPException | None = None

    _executing_run_ids[run_id] = "__run_tab__"
    for it in items:
        _executing_item_ids.add(str(it["id"]))
    try:
        await _execute_session_start(
            run_id=run_id,
            item_id=str(items[0]["id"]),
            agent_tab_id=agent_tab,
            human_tab_id=human_tab,
            handoff_url=str(ctx.get("handoff_url") or ""),
        )
        record(
            "agent.execute_run_started",
            run_id,
            cfg=cfg,
            measure={"item_count": len(items)},
            flags={"mode": "run_tab"},
            item_ids=[str(i["id"]) for i in items],
        )

        from .execute_run import run_host_execute_run_loop

        # Abort flag visible to loop via ctx poll each step.
        async def _poll_abort() -> None:
            while run_id in _executing_run_ids:
                if _run_abort_flags.get(run_id):
                    rs = ctx.get("run_state")
                    if isinstance(rs, dict):
                        rs["abort"] = True
                    ctx["_abort"] = True
                    return
                await asyncio.sleep(0.5)

        abort_task = asyncio.create_task(_poll_abort())
        try:
            result = await run_host_execute_run_loop(items, ctx)
        finally:
            abort_task.cancel()
            with suppress(asyncio.CancelledError):
                await abort_task

        usage = usage_measure((result or {}).get("usage"))
        browser_after = _browser_results_for_run(run_id)
        if cfg.hermes.execute_require_browser_evidence and browser_after <= browser_before:
            err = "execute run completed without browser evidence"
            record(
                "agent.execute_run_finished",
                run_id,
                cfg=cfg,
                error=err,
                measure=usage or None,
                flags={"outcome": "no_browser_evidence"},
            )
            for it in items:
                iid = str(it["id"])
                cur = _work_items.get(iid)
                if cur and cur.get("status") == "running":
                    try:
                        await _patch_work_item(
                            iid, status="failed", run_id=run_id, last_error=err
                        )
                    except ExtensionNotConnectedError:
                        pass
            raise HTTPException(status_code=422, detail=err)

        paused = bool((result or {}).get("paused"))
        if paused:
            preserve_tabs = True
            record(
                "agent.execute_run_finished",
                run_id,
                cfg=cfg,
                measure=usage or None,
                flags={"outcome": "paused"},
                completed_ids=(result or {}).get("completed_ids"),
                remaining_ids=(result or {}).get("remaining_ids"),
            )
            # Reset non-paused remaining to proposed for Resume tab.
            for iid in (result or {}).get("remaining_ids") or []:
                cur = _work_items.get(str(iid))
                if cur and cur.get("status") == "running":
                    try:
                        await _patch_work_item(
                            str(iid), status="proposed", run_id=run_id
                        )
                    except ExtensionNotConnectedError:
                        pass
            return {
                "ok": True,
                "paused": True,
                "summary": (result or {}).get("summary"),
                "completed_ids": (result or {}).get("completed_ids"),
                "remaining_ids": (result or {}).get("remaining_ids"),
                "usage": usage,
            }

        record(
            "agent.execute_run_finished",
            run_id,
            cfg=cfg,
            measure=usage or None,
            flags={"outcome": "done"},
            summary_snippet=str((result or {}).get("summary") or "")[
                : cfg.prompts.event_summary_snippet_max_chars
            ],
            completed_ids=(result or {}).get("completed_ids"),
            failed_ids=(result or {}).get("failed_ids"),
        )
        record("run.finished", run_id, cfg=cfg, measure=usage or None)
        return {
            "ok": True,
            "paused": False,
            "summary": (result or {}).get("summary"),
            "completed_ids": (result or {}).get("completed_ids"),
            "failed_ids": (result or {}).get("failed_ids"),
            "usage": usage,
        }
    except Exception as exc:
        if isinstance(exc, HTTPException):
            # Ensure running items are not left stuck after intentional 4xx.
            detail = str(exc.detail)[: cfg.prompts.event_snippet_max_chars]
            for it in items:
                iid = str(it["id"])
                cur = _work_items.get(iid)
                if cur and cur.get("status") == "running":
                    try:
                        await _patch_work_item(
                            iid, status="failed", run_id=run_id, last_error=detail
                        )
                    except ExtensionNotConnectedError:
                        pass
            raise
        err = str(exc)[: cfg.prompts.event_snippet_max_chars]
        status = 500
        if isinstance(exc, HostExecuteError):
            low = err.lower()
            if (
                low.startswith("partial:")
                or "incomplete" in low
                or "no tab" in low
                or "initial scrape" in low
                or "cancelled" in low
            ):
                status = 422
        record(
            "agent.execute_run_finished",
            run_id,
            cfg=cfg,
            error=err,
            flags={"outcome": "failed"},
        )
        for it in items:
            iid = str(it["id"])
            cur = _work_items.get(iid)
            if cur and cur.get("status") == "running":
                try:
                    await _patch_work_item(
                        iid, status="failed", run_id=run_id, last_error=err
                    )
                except ExtensionNotConnectedError:
                    pass
        http_exc = HTTPException(status_code=status, detail=err)
        raise http_exc from exc
    finally:
        for it in items:
            _executing_item_ids.discard(str(it["id"]))
        _executing_run_ids.pop(run_id, None)
        _run_abort_flags.pop(run_id, None)
        _execute_session_end(run_id)
        try:
            live_agent = (ctx or {}).get("agent_tab_id", agent_tab)
            live_human = (ctx or {}).get("human_tab_id", human_tab)
            await _execute_cleanup(
                run_id=run_id,
                item_id=str(items[0]["id"]),
                agent_tab_id=live_agent,
                human_tab_id=live_human,
                preserve_tabs=preserve_tabs,
            )
        except Exception:  # noqa: BLE001
            pass


@app.post("/v1/runs/{run_id}/execute/cancel")
async def execute_run_cancel(run_id: str) -> dict[str, Any]:
    if run_id not in _executing_run_ids:
        return {"ok": True, "cancelled": False, "note": "no execute in progress"}
    _run_abort_flags[run_id] = True
    return {"ok": True, "cancelled": True}


@app.post("/v1/items/{item_id}/execute")
async def execute_item(item_id: str, body: ExecuteBody) -> dict[str, Any]:
    item = _work_items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="work item not found")
    if item.get("column") != "agent":
        raise HTTPException(status_code=400, detail="execute only for agent column")
    if item_id in _executing_item_ids:
        raise HTTPException(
            status_code=409,
            detail="execute already in progress for this item",
        )
    if body.run_id in _executing_run_ids:
        other = _executing_run_ids[body.run_id]
        raise HTTPException(
            status_code=409,
            detail=f"execute already in progress for this run ({other})",
        )
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
    snap = await _memory_get(body.run_id)
    cfg = get_config()
    memory_slice = format_for_execute(
        snap["memory"],
        body.run_id,
        decomposition=str(meta.get("decomposition") or ""),
        semantic=snap["semantic"],
        packet_max_facts=cfg.memory.semantic_packet_max_facts,
        max_key_chars=cfg.memory.semantic_max_key_chars,
        max_value_chars=cfg.memory.semantic_max_value_chars,
    )
    ctx.update(memory_slice)
    vault = snap.get("vault") if isinstance(snap.get("vault"), dict) else {"files": []}
    ctx["vault"] = {
        "files": list(vault.get("files") or [])[:20],
        "note": (
            "Operator-supplied files. Use upload(vault_id, target_id) for kind:file Eyes. "
            "If vault is empty and a site needs an attachment, park You (human_remainder)."
        ),
    }
    backend = get_backend()
    execute_fn = getattr(backend, "execute_item", None)
    use_host_loop = str(cfg.execute.runtime or "").strip().lower() == "host_loop"
    if not use_host_loop and not execute_fn:
        raise HTTPException(status_code=501, detail="backend does not support execute")
    browser_before = _browser_results_for_run(body.run_id)
    _execute_ops[body.run_id] = []
    _failed_ops[body.run_id] = []
    _last_probe_links_empty[body.run_id] = False
    _executing_item_ids.add(item_id)
    _executing_run_ids[body.run_id] = item_id
    if item.get("resume_ready") or item.get("cleared_gates"):
        cleared_gates = list(item.get("cleared_gates") or [])
        ctx["resume"] = {
            "ready": bool(item.get("resume_ready")),
            "cleared_gates": cleared_gates,
            "note": (
                "Human cleared these gate URLs. Do not mint another You card for them; "
                "continue agent work past the gate (open destination with --url if needed)."
            ),
        }
        if item.get("resume_ready"):
            cleared = {**item, "resume_ready": False}
            _work_items[item_id] = cleared
            item = cleared
    await _execute_session_start(
        run_id=body.run_id,
        item_id=item_id,
        agent_tab_id=ctx.get("agent_tab_id"),
        human_tab_id=ctx.get("human_tab_id"),
        handoff_url=str(ctx.get("handoff_url") or ""),
    )
    record(
        "agent.execute_started",
        body.run_id,
        cfg=cfg,
        item_id=item_id,
        measure={
            "semantic_fact_count": len(memory_slice.get("semantic_facts") or []),
            "recent_execution_count": len(memory_slice.get("recent_executions") or []),
            "notepad_bullet_count": len(
                (memory_slice.get("run_notepad") or {}).get("bullets") or []
            ),
        },
        flags={
            "has_semantic_facts": bool(memory_slice.get("semantic_facts")),
        },
    )
    http_exc: HTTPException | None = None
    preserve_tabs = False
    try:
        try:
            if use_host_loop:
                from .execute_loop import run_host_execute_loop

                result = await run_host_execute_loop(item, ctx)
            else:
                result = await execute_fn(item, ctx)
        except Exception as exc:
            err = str(exc)[: cfg.prompts.event_snippet_max_chars]
            outcome = "failed"
            if (
                isinstance(exc, (HermesExecuteError, HostExecuteError))
                and getattr(exc, "empty_output", False)
            ):
                outcome = "empty_output"
            _record_execute_failed_event(
                run_id=body.run_id,
                item_id=item_id,
                err=err,
                exc=exc,
                outcome=outcome,
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
            # Partial / incomplete / dead-tab are client-visible execute outcomes (422),
            # not Host crashes (500).
            status = 500
            if isinstance(exc, (HermesExecuteError, HostExecuteError)):
                low = err.lower()
                if (
                    low.startswith("partial:")
                    or "incomplete" in low
                    or "no tab" in low
                    or "initial scrape" in low
                    or "tab missing" in low
                    or "agent tab" in low
                ):
                    status = 422
            http_exc = HTTPException(status_code=status, detail=err)
            raise http_exc from exc
        browser_after = _browser_results_for_run(body.run_id)
        usage = usage_measure((result or {}).get("usage"))
        if cfg.hermes.execute_require_browser_evidence and browser_after <= browser_before:
            err = "execute completed without browser evidence"
            record(
                "agent.execute_failed",
                body.run_id,
                cfg=cfg,
                item_id=item_id,
                error=err,
                measure=usage or None,
                flags={"outcome": "no_browser_evidence"},
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
        if not incomplete:
            incomplete = failed_open_tab_blocks_done(
                failed_ops=list(_failed_ops.get(body.run_id, [])),
                summary=str(evidence["summary"] or ""),
            )
        gate_you = open_auth_gate_you(item_id, _work_items)
        remainder_you = open_you_remainder(item_id, _work_items)
        if not incomplete:
            incomplete = auth_gate_blocks_false_closure(
                str(evidence["summary"] or ""),
                has_auth_gate_you=bool(gate_you or remainder_you),
            )
        if not incomplete:
            incomplete = human_judgment_blocks_false_closure(
                str(evidence["summary"] or ""),
                item_title=str(
                    item.get("title")
                    or (_work_items.get(item_id) or {}).get("title")
                    or ""
                ),
                has_you_remainder=bool(remainder_you or gate_you),
            )
        # Auth-gate You already parked: keep awaiting_human (Resume path), never fail→Retry.
        if incomplete and gate_you:
            incomplete = None
            park_for_gate = True
        else:
            park_for_gate = False
        # human_remainder You already minted: waive open-only observation only
        # (do not waive false-closure / openTab-failed / empty-probe gates).
        if (
            incomplete
            and remainder_you
            and not gate_you
            and "open-only observation" in incomplete
        ):
            incomplete = None
        if incomplete:
            err = incomplete if incomplete.lower().startswith("partial:") else f"Partial: {incomplete}"
            record(
                "agent.execute_failed",
                body.run_id,
                cfg=cfg,
                item_id=item_id,
                error=err,
                measure=usage or None,
                flags={"outcome": "incomplete"},
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
                measure=usage or None,
            )
            return {
                "ok": False,
                "work_item_id": item_id,
                "status": "running",
                "blocked": blocked,
                "result": result,
            }

        # Auth/challenge park: halt parent until human clears gate (not Completed).
        # Keep agent tab open for Show-tab custody until Mark done → Resume.
        if (
            park_for_gate
            or gate_you
            or current.get("status") == "awaiting_human"
        ):
            preserve_tabs = True
            await _patch_work_item(
                item_id,
                status="awaiting_human",
                run_id=body.run_id,
                evidence=evidence,
                clear_last_error=True,
            )
            await _record_execute_memory(
                run_id=body.run_id,
                item=item,
                outcome="awaiting_human",
                summary=str(evidence["summary"] or ""),
            )
            record(
                "agent.executed",
                body.run_id,
                cfg=cfg,
                measure={
                    "browser_ops": evidence["browser_ops"],
                    "exit_code": (result or {}).get("exit_code"),
                    **usage,
                },
                flags={"awaiting_human": True, "preserve_tabs": True, "outcome": "awaiting_human"},
                item_id=item_id,
                summary_snippet=evidence["summary"][
                    : cfg.prompts.event_summary_snippet_max_chars
                ],
            )
            return {
                "ok": True,
                "work_item_id": item_id,
                "status": "awaiting_human",
                "result": result,
            }

        await _patch_work_item(
            item_id,
            status="done",
            run_id=body.run_id,
            evidence=evidence,
            clear_last_error=True,
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
                **usage,
            },
            flags={"outcome": "done"},
            item_id=item_id,
            summary_snippet=evidence["summary"][: cfg.prompts.event_summary_snippet_max_chars],
        )
        record(
            "run.finished",
            body.run_id,
            cfg=cfg,
            backend=os.environ.get("DESK_AGENT_BACKEND", "mock"),
            item_id=item_id,
            measure=usage or None,
        )
        return {"ok": True, "work_item_id": item_id, "status": "done", "result": result}
    finally:
        _executing_item_ids.discard(item_id)
        if _executing_run_ids.get(body.run_id) == item_id:
            _executing_run_ids.pop(body.run_id, None)
        _execute_session_end(body.run_id, item_id)
        # Auth-gate You may have been minted mid-execute even if the run later
        # failed (no browser evidence / exception). Keep the agent tab for Show.
        if not preserve_tabs and open_auth_gate_you(item_id, _work_items):
            preserve_tabs = True
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

    shot = body.viewport_shot if isinstance(body.viewport_shot, dict) else None
    shot_b64 = (shot or {}).get("base64") or ""
    complete_measure: dict[str, Any] = {}
    complete_flags: dict[str, Any] = {}
    if shot_b64:
        complete_measure["viewport_shot_bytes"] = len(shot_b64)
        complete_flags["has_viewport_shot"] = True
    elif body.viewport_shot is not None:
        complete_flags["has_viewport_shot"] = False
    if body.shot_on_agent_tab is not None:
        complete_flags["shot_on_agent_tab"] = bool(body.shot_on_agent_tab)
    record(
        "item.completed",
        body.run_id,
        cfg=get_config(),
        item_id=item_id,
        column="you",
        measure=complete_measure or None,
        flags=complete_flags or None,
    )

    resume_parent_id = None
    parent_id = item.get("parent_id")
    if parent_id and (item.get("resume") or item.get("park_kind") == "auth_gate"):
        parent = _work_items.get(parent_id)
        if parent and parent.get("status") == "awaiting_human":
            gate_url = ((item.get("source") or {}).get("url")) or ""
            await _patch_work_item(
                parent_id,
                status="proposed",
                run_id=body.run_id,
                clear_last_error=True,
            )
            # Flag for panel Resume label (cleared on next execute start implicitly via status flow).
            parent_now = _work_items.get(parent_id)
            if parent_now is not None:
                parent_now["resume_ready"] = True
                gates = list(parent_now.get("cleared_gates") or [])
                gates.append(
                    {
                        "url": gate_url,
                        "park_kind": item.get("park_kind") or "auth_gate",
                        "you_item_id": item_id,
                        "title": item.get("title") or "",
                    }
                )
                parent_now["cleared_gates"] = gates[-20:]
                parent_now.pop("last_error", None)
                _work_items[parent_id] = parent_now
                await _send_board_patch(
                    body.run_id,
                    uuid.uuid4().hex,
                    [{"op": "update", "item": parent_now}],
                    required=True,
                )
            resume_parent_id = parent_id
            try:
                await _memory_patch(
                    [
                        {
                            "op": "append_bullet",
                            "run_id": body.run_id,
                            "bullet": f"Human cleared gate for {gate_url or parent_id}; resume agent.",
                        }
                    ]
                )
            except Exception:
                pass
            resume_flags: dict[str, Any] = {"from_you": item_id}
            resume_flags.update(complete_flags)
            record(
                "agent.resume_ready",
                body.run_id,
                cfg=get_config(),
                item_id=parent_id,
                measure=complete_measure or None,
                flags=resume_flags,
            )

    out: dict[str, Any] = {"ok": True, "work_item_id": item_id, "status": "done"}
    if resume_parent_id:
        out["resume_parent_id"] = resume_parent_id
    return out


@app.post("/v1/items/{item_id}/tab_custody")
async def tab_custody(item_id: str, body: TabCustodyBody) -> dict[str, Any]:
    """Extension reports park/reveal of agent tab lent to human (observability only)."""
    item = _work_items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="work item not found")
    action = (body.action or "").strip().lower()
    if action not in ("park", "reveal"):
        raise HTTPException(status_code=400, detail="action must be park|reveal")
    shot = body.viewport_shot if isinstance(body.viewport_shot, dict) else None
    shot_b64 = (shot or {}).get("base64") or ""
    measure: dict[str, Any] = {}
    if shot_b64:
        measure["viewport_shot_bytes"] = len(shot_b64)
    flags: dict[str, Any] = {"action": action, "has_viewport_shot": bool(shot_b64)}
    if isinstance(body.flags, dict):
        for k, v in body.flags.items():
            if k not in flags:
                flags[k] = v
    record(
        "tab.custody",
        body.run_id,
        cfg=get_config(),
        item_id=item_id,
        agent_tab_id=body.agent_tab_id,
        measure=measure or None,
        flags=flags,
    )
    return {"ok": True, "item_id": item_id, "action": action}


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
                extra = _obs_from_pending_command(
                    cid, run_id=str(run_id or ""), result=result
                )
                record(
                    "browser.command_result",
                    run_id,
                    cfg=cfg,
                    include_limits=False,
                    measure=fields["measure"],
                    flags=fields["flags"],
                    **fields["detail"],
                    **extra,
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
                elif run_id:
                    failed_op = str(op_name or result.get("op") or "")
                    if failed_op:
                        _failed_ops.setdefault(run_id, []).append(failed_op)
                    if cid:
                        _command_ops.pop(cid or "", None)
                        _command_evidence_flags.pop(cid or "", None)
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
