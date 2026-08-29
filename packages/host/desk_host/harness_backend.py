"""Execute Desk browser ops via real browser-harness (Way 1 everyday Chrome).

Does not set BU_CDP_URL to Virgil isolated ports (:9223). Uses BU_NAME so Desk
does not share Virgil tick's harness daemon. Sticky CDP target per run_id —
no per-call ``with tab(url):`` auto-close (that would break multi-turn execute).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


HARNESS_OPS = frozenset(
    {"observe", "click", "fill", "scroll", "key", "scrape", "screenshot"}
)

# Ops that still require the MV3 extension even when driver=harness.
EXTENSION_OPS = frozenset(
    {
        "openTab",
        "duplicateTab",
        "navigate",
        "captureHandoffSnapshot",
    }
)


class HarnessBackendError(RuntimeError):
    """Raised when browser-harness fails or Way 1 attach is incomplete."""


@dataclass
class StickyTarget:
    target_id: str
    url: str
    opened_by_harness: bool = False


@dataclass
class HarnessSessionStore:
    """In-memory sticky CDP targets keyed by run_id."""

    targets: dict[str, StickyTarget] = field(default_factory=dict)

    def get(self, run_id: str) -> StickyTarget | None:
        return self.targets.get(run_id)

    def set(self, run_id: str, sticky: StickyTarget) -> None:
        self.targets[run_id] = sticky

    def pop(self, run_id: str) -> StickyTarget | None:
        return self.targets.pop(run_id, None)

    def clear(self) -> None:
        self.targets.clear()


_sessions = HarnessSessionStore()

# Optional override for unit tests (callable like run_harness_script).
_run_script_override: Any | None = None


def reset_for_tests() -> None:
    _sessions.clear()
    global _run_script_override
    _run_script_override = None


def set_run_script_override(fn: Any | None) -> None:
    global _run_script_override
    _run_script_override = fn


def is_harness_op(op: str) -> bool:
    return op in HARNESS_OPS


def uses_harness_driver(driver: str) -> bool:
    return (driver or "").strip().lower() == "harness"


def map_connection_error(message: str) -> str:
    """Map harness/doctor stderr into operator-actionable text."""
    text = (message or "").strip()
    low = text.lower()
    if "allow remote debugging" in low or "remote-debugging" in low:
        return (
            "browser-harness cannot attach to everyday Chrome (Way 1). "
            "Open chrome://inspect/#remote-debugging, tick Allow remote debugging, "
            "and click Allow on the Chrome 144+ popup. "
            f"Detail: {text[:1500]}"
        )
    if "devtoolsactiveport" in low or "daemon" in low and "fail" in low:
        return (
            "browser-harness daemon/Chrome attach failed. "
            "Run: BU_NAME=virgil-desk browser-harness --doctor "
            "(do not point BU_CDP_URL at Virgil :9223 for Desk). "
            f"Detail: {text[:1500]}"
        )
    if "not found" in low and "browser-harness" in low:
        return text
    return text[:2000] if text else "browser-harness failed"


def _strip_virgil_cdp_env(env: dict[str, str]) -> dict[str, str]:
    """Never inherit Virgil isolated Chrome CDP endpoints for Desk Way 1."""
    out = dict(env)
    for key in ("BU_CDP_URL", "BU_CDP_WS"):
        val = (out.get(key) or "").strip()
        if not val:
            out.pop(key, None)
            continue
        if "9223" in val or "chrome-virgil" in val.lower():
            out.pop(key, None)
            continue
        # Way 1 discovers DevToolsActivePort; drop explicit URL so everyday Chrome wins.
        out.pop(key, None)
    return out


def run_harness_script(
    python_source: str,
    *,
    harness_bin: str,
    bu_name: str,
    timeout_sec: float = 60.0,
) -> str:
    if _run_script_override is not None:
        return _run_script_override(
            python_source,
            harness_bin=harness_bin,
            bu_name=bu_name,
            timeout_sec=timeout_sec,
        )
    if not python_source.strip():
        raise HarnessBackendError("Empty browser-harness script")
    env = _strip_virgil_cdp_env(os.environ.copy())
    env["BU_NAME"] = bu_name or "virgil-desk"
    try:
        result = subprocess.run(
            [harness_bin],
            input=python_source,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise HarnessBackendError(
            f"{harness_bin!r} not found on PATH. Install browser-harness and run "
            f"BU_NAME={bu_name} {harness_bin} --doctor."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or exc.stderr or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        raise HarnessBackendError(
            map_connection_error(
                f"browser-harness timed out after {timeout_sec}s: {str(partial).strip()[:1500]}"
            )
        ) from exc

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise HarnessBackendError(
            map_connection_error(
                f"browser-harness exited {result.returncode}: {err[:2000]}"
            )
        )
    return result.stdout


def _parse_json_stdout(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        raise HarnessBackendError("browser-harness returned empty output")
    # Prefer last JSON object line (harness may print banners).
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    # Whole stdout as JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HarnessBackendError(
            f"browser-harness stdout was not JSON: {text[:500]}"
        ) from exc
    if not isinstance(parsed, dict):
        raise HarnessBackendError("browser-harness JSON was not an object")
    return parsed


def _resolve_seed_url(command: dict[str, Any]) -> str:
    url = (command.get("url") or command.get("handoff_url") or "").strip()
    if url:
        return url
    params = command.get("params") or {}
    if isinstance(params, dict):
        return str(params.get("url") or "").strip()
    return ""


def build_ensure_target_script(
    *,
    seed_url: str,
    existing_target_id: str | None,
) -> str:
    """Attach to sticky target or find/create a page for seed_url."""
    return f"""
import json
seed = {json.dumps(seed_url)}
existing = {json.dumps(existing_target_id)}
opened = False
tid = existing

def _key(u):
    from urllib.parse import urlparse
    try:
        p = urlparse(u or "")
        return (p.scheme + "://" + p.netloc + p.path).rstrip("/")
    except Exception:
        return (u or "").rstrip("/")

if tid:
    try:
        switch_tab(tid)
    except Exception:
        tid = None

if not tid:
    want = _key(seed)
    match = None
    for t in list_tabs(include_chrome=False):
        if want and _key(t.get("url") or "") == want:
            match = t["targetId"]
            break
    if match:
        tid = match
        switch_tab(tid)
    elif seed:
        tid = new_tab(seed)
        wait_for_load()
        opened = True
    else:
        cur = current_tab()
        tid = cur["targetId"]
        switch_tab(tid)

info = page_info()
print(json.dumps({{
    "ok": True,
    "target_id": tid,
    "opened_by_harness": opened,
    "url": info.get("url") or seed,
    "title": info.get("title") or "",
}}))
"""


_OP_SCRIPT_TEMPLATE = r'''
import json, base64
from pathlib import Path

params = __PARAMS__
tid = __TID__
shot_path = __SHOT__
skip_screenshot = __SKIP__
excerpt_max = __EXCERPT_MAX__
op = __OP__

switch_tab(tid)
before = page_info()
url_before = before.get("url") or ""
title = before.get("title") or ""
act_resolved = None
ok = True
error = None
used = "none"

def _click_selector(sel):
    global used
    try:
        click_element(str(sel))
        used = "selector"
        return
    except NameError:
        pass
    expr = (
        "(()=>{const e=document.querySelector(%s);"
        "if(!e)return null;e.scrollIntoView({block:'center'});"
        "const r=e.getBoundingClientRect();"
        "return {x:r.left+r.width/2,y:r.top+r.height/2};})()"
    ) % json.dumps(str(sel))
    rect = js(expr)
    if not rect:
        raise RuntimeError("selector not found: " + str(sel))
    click_at_xy(float(rect["x"]), float(rect["y"]))
    used = "selector"

def _fill_selector(sel, value):
    try:
        set_field(str(sel), str(value))
        return
    except NameError:
        fill_input(str(sel), str(value))

try:
    if op in ("observe", "scrape", "screenshot"):
        pass
    elif op == "click":
        x, y = params.get("x"), params.get("y")
        sel = params.get("selector") or params.get("css")
        if x is not None and y is not None:
            click_at_xy(float(x), float(y))
            used = "xy"
        elif sel:
            _click_selector(sel)
        else:
            ok = False
            error = "click requires x/y or selector (harness driver; target_id text match unsupported)"
            used = "none"
    elif op == "fill":
        sel = params.get("selector") or params.get("css")
        value = params.get("value")
        if value is None:
            value = params.get("text") or ""
        if not sel:
            ok = False
            error = "fill requires selector (harness driver)"
            used = "none"
        else:
            _fill_selector(sel, value)
            used = "selector"
            pk = params.get("press_key")
            if pk:
                press_key(str(pk))
    elif op == "scroll":
        direction = (params.get("direction") or "down").lower()
        dy = int(params.get("dy") or 0)
        if not dy:
            dy = 400 if direction == "down" else (-400 if direction == "up" else 0)
        dx = int(params.get("dx") or 0)
        if direction == "left":
            dx = dx or -400
        elif direction == "right":
            dx = dx or 400
        info = page_info()
        scroll(info.get("sx") or 0, info.get("sy") or 0, dy=dy, dx=dx)
        used = "scroll"
    elif op == "key":
        press_key(str(params.get("key") or "Enter"))
        used = "key"
    else:
        ok = False
        error = "unsupported harness op"
except Exception as exc:
    ok = False
    error = str(exc)

after = page_info()
url_after = after.get("url") or url_before
title = after.get("title") or title

text = ""
try:
    text = js("document.body && document.body.innerText || ''") or ""
except Exception:
    text = ""
if isinstance(text, str) and len(text) > excerpt_max:
    text = text[:excerpt_max]

screenshot = None
if (not skip_screenshot) and shot_path:
    try:
        path = capture_screenshot(shot_path, max_dim=1600)
        raw = Path(path).read_bytes()
        dpr = js("window.devicePixelRatio") or 1
        screenshot = {
            "mime": "image/png",
            "base64": base64.b64encode(raw).decode("ascii"),
            "css_width": after.get("w") or js("innerWidth") or 0,
            "css_height": after.get("h") or js("innerHeight") or 0,
            "device_pixel_ratio": dpr,
            "width": None,
            "height": None,
        }
    except Exception as exc:
        if op in ("observe", "screenshot"):
            ok = False
            error = ((error + "; ") if error else "") + ("screenshot failed: %s" % exc)

if op in ("click", "fill", "scroll", "key"):
    act_resolved = {
        "op": op,
        "requested": params,
        "used": used if ok else "none",
        "url_before": url_before,
        "url_after": url_after,
    }
    if error:
        act_resolved["error"] = error

out = {
    "ok": ok,
    "url": url_after,
    "title": title,
    "scrape_excerpt": text,
    "text_omitted": False,
    "eyes": "harness",
    "driver": "harness",
    "interact_targets": [],
    "scroll_containers": [],
    "viewport": {"w": after.get("w"), "h": after.get("h")},
    "device_pixel_ratio": js("window.devicePixelRatio") or 1,
}
if screenshot:
    out["screenshot"] = screenshot
if act_resolved is not None:
    out["act_resolved"] = act_resolved
if error and not ok:
    out["error"] = error
if op == "observe":
    out["observe"] = {
        "url": url_after,
        "title": title,
        "viewport": out["viewport"],
        "device_pixel_ratio": out["device_pixel_ratio"],
        "text_excerpt": text,
        "text_omitted": False,
        "interact_targets": [],
        "scroll_containers": [],
        "eyes": "harness",
    }
    if screenshot:
        out["observe"]["screenshot"] = {
            "omitted": False,
            "css_width": screenshot.get("css_width"),
            "css_height": screenshot.get("css_height"),
            "device_pixel_ratio": screenshot.get("device_pixel_ratio"),
            "mime": screenshot.get("mime"),
        }

print(json.dumps(out))
'''


def build_op_script(
    op: str,
    params: dict[str, Any],
    *,
    target_id: str,
    screenshot_path: str | None,
    skip_screenshot: bool,
    excerpt_max: int,
) -> str:
    """Script that assumes sticky target already attached; prints Desk-shaped JSON."""
    return (
        _OP_SCRIPT_TEMPLATE.replace("__PARAMS__", json.dumps(params))
        .replace("__TID__", json.dumps(target_id))
        .replace("__SHOT__", json.dumps(screenshot_path))
        .replace("__SKIP__", "True" if skip_screenshot else "False")
        .replace("__EXCERPT_MAX__", str(int(excerpt_max)))
        .replace("__OP__", json.dumps(op))
    )


def build_release_script(target_id: str, *, opened_by_harness: bool) -> str:
    if not opened_by_harness:
        return f"""
import json
# Sticky target was an existing everyday tab — leave it open.
print(json.dumps({{"ok": True, "released": False, "target_id": {json.dumps(target_id)}}}))
"""
    return f"""
import json
tid = {json.dumps(target_id)}
try:
    close_tab(tid, strict=False)
except Exception:
    pass
print(json.dumps({{"ok": True, "released": True, "target_id": tid}}))
"""


def release_run(
    run_id: str,
    *,
    harness_bin: str,
    bu_name: str,
    timeout_sec: float = 30.0,
) -> None:
    sticky = _sessions.pop(run_id)
    if not sticky:
        return
    try:
        run_harness_script(
            build_release_script(
                sticky.target_id, opened_by_harness=sticky.opened_by_harness
            ),
            harness_bin=harness_bin,
            bu_name=bu_name,
            timeout_sec=timeout_sec,
        )
    except HarnessBackendError:
        # Best-effort cleanup — do not fail execute teardown.
        pass


def run_browser_op(
    command: dict[str, Any],
    *,
    harness_bin: str,
    bu_name: str,
    timeout_sec: float = 60.0,
    excerpt_max: int = 100_000,
    skip_screenshot: bool = False,
    shot_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Run one Desk browser command via harness. Returns a command_result-shaped dict.
    """
    started = time.time()
    op = str(command.get("op") or "")
    cid = str(command.get("command_id") or "")
    run_id = str(command.get("run_id") or "")
    params = command.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    if not is_harness_op(op):
        raise HarnessBackendError(f"op {op!r} is not a harness execute op")

    seed = _resolve_seed_url(command)
    sticky = _sessions.get(run_id) if run_id else None

    ensure = build_ensure_target_script(
        seed_url=seed or (sticky.url if sticky else ""),
        existing_target_id=sticky.target_id if sticky else None,
    )
    ensure_out = _parse_json_stdout(
        run_harness_script(
            ensure,
            harness_bin=harness_bin,
            bu_name=bu_name,
            timeout_sec=timeout_sec,
        )
    )
    tid = str(ensure_out.get("target_id") or "")
    if not tid:
        raise HarnessBackendError("harness did not return target_id")
    opened = bool(ensure_out.get("opened_by_harness"))
    if sticky and sticky.opened_by_harness:
        opened = True
    if run_id:
        _sessions.set(
            run_id,
            StickyTarget(
                target_id=tid,
                url=str(ensure_out.get("url") or seed or ""),
                opened_by_harness=opened,
            ),
        )

    shot_path: str | None = None
    if not skip_screenshot:
        base = shot_dir or Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
        shot_path = str(base / f"virgil-desk-{run_id or 'run'}-{cid or 'cmd'}.png")

    op_script = build_op_script(
        op,
        params,
        target_id=tid,
        screenshot_path=shot_path,
        skip_screenshot=skip_screenshot
        or bool(command.get("skip_screenshot")),
        excerpt_max=excerpt_max,
    )
    payload = _parse_json_stdout(
        run_harness_script(
            op_script,
            harness_bin=harness_bin,
            bu_name=bu_name,
            timeout_sec=timeout_sec,
        )
    )

    # Drop temp PNG after embedding base64 (evidence path may persist later).
    if shot_path:
        try:
            Path(shot_path).unlink(missing_ok=True)
        except OSError:
            pass

    result: dict[str, Any] = {
        "command_id": cid,
        "ok": bool(payload.get("ok", True)),
        "op": op,
        "url": payload.get("url"),
        "title": payload.get("title"),
        "scrape_excerpt": payload.get("scrape_excerpt") or "",
        "text_omitted": bool(payload.get("text_omitted")),
        "interact_targets": payload.get("interact_targets") or [],
        "scroll_containers": payload.get("scroll_containers") or [],
        "viewport": payload.get("viewport"),
        "device_pixel_ratio": payload.get("device_pixel_ratio"),
        "eyes": "harness",
        "driver": "harness",
        "duration_ms": int((time.time() - started) * 1000),
    }
    if payload.get("screenshot"):
        result["screenshot"] = payload["screenshot"]
    if payload.get("observe"):
        result["observe"] = payload["observe"]
    if payload.get("act_resolved"):
        result["act_resolved"] = payload["act_resolved"]
    if payload.get("error"):
        result["error"] = payload["error"]
        result["ok"] = False
    if result.get("act_resolved") and result["act_resolved"].get("used") == "none":
        result["ok"] = False
    return result
