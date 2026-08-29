"""Thin /v1/browser payloads before Hermes sees them via desk-browser CLI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _thin_screenshot(shot: Any) -> dict[str, Any] | None:
    if not isinstance(shot, dict):
        return None
    out: dict[str, Any] = {"omitted": True}
    for key in ("width", "height", "css_width", "css_height", "device_pixel_ratio", "mime"):
        if key in shot and shot[key] is not None:
            out[key] = shot[key]
    return out


def _thin_result_body(result: dict[str, Any]) -> dict[str, Any]:
    """Strip screenshot base64; keep Eyes/Hands fields Hermes needs to act."""
    thinned = deepcopy(result)
    shot = thinned.get("screenshot")
    ref = thinned.get("screenshot_ref")
    if shot is not None or ref:
        stub = _thin_screenshot(shot) if isinstance(shot, dict) else {"omitted": True}
        if stub is None:
            stub = {"omitted": True}
        if ref:
            stub["screenshot_ref"] = ref
        thinned["screenshot"] = stub
        # Keep screenshot_ref at result top-level if present (host persistence).
        if ref:
            thinned["screenshot_ref"] = ref

    observe = thinned.get("observe")
    if isinstance(observe, dict) and "screenshot" in observe:
        observe = dict(observe)
        observe["screenshot"] = _thin_screenshot(observe.get("screenshot")) or {
            "omitted": True
        }
        thinned["observe"] = observe

    return thinned


def thin_browser_response(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Return a Hermes-safe copy of a /v1/browser wait response.

    Does not mutate the original. Extension/host evidence paths are unchanged;
    only CLI stdout should use this.
    """
    out = deepcopy(payload)
    result = out.get("result")
    if isinstance(result, dict):
        out["result"] = _thin_result_body(result)
    elif "screenshot" in out or "screenshot_ref" in out:
        # Some callers flatten CommandResult at the top level.
        out = _thin_result_body(out)
    return out
