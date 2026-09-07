"""Thin /v1/browser payloads before Hermes sees them via desk-browser CLI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Hermes Eyes: keep act handles only (coords stay in extension targetMap).
_TARGET_KEEP = frozenset({"id", "ref", "kind", "label", "frame_id"})


def _thin_screenshot(shot: Any) -> dict[str, Any] | None:
    if not isinstance(shot, dict):
        return None
    out: dict[str, Any] = {"omitted": True}
    for key in ("width", "height", "css_width", "css_height", "device_pixel_ratio", "mime"):
        if key in shot and shot[key] is not None:
            out[key] = shot[key]
    return out


def _thin_interact_target(t: Any) -> dict[str, Any]:
    if not isinstance(t, dict):
        return {}
    return {k: t[k] for k in _TARGET_KEEP if k in t and t[k] is not None}


def _thin_interact_targets(targets: Any) -> list[dict[str, Any]]:
    if not isinstance(targets, list):
        return []
    return [_thin_interact_target(t) for t in targets if isinstance(t, dict)]


def _thin_scroll_containers(containers: Any) -> list[dict[str, Any]]:
    if not isinstance(containers, list):
        return []
    out: list[dict[str, Any]] = []
    for c in containers:
        if not isinstance(c, dict):
            continue
        slim = {
            k: c[k]
            for k in ("id", "ref", "label", "scrollHeight", "clientHeight", "frame_id")
            if k in c and c[k] is not None
        }
        out.append(slim)
    return out


def _thin_result_body(result: dict[str, Any]) -> dict[str, Any]:
    """Strip screenshot base64 and fat target geometry; keep Eyes/Hands Hermes needs."""
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
        if ref:
            thinned["screenshot_ref"] = ref

    if "interact_targets" in thinned:
        thinned["interact_targets"] = _thin_interact_targets(thinned.get("interact_targets"))
    if "scroll_containers" in thinned:
        thinned["scroll_containers"] = _thin_scroll_containers(
            thinned.get("scroll_containers")
        )

    observe = thinned.get("observe")
    if isinstance(observe, dict):
        observe = dict(observe)
        if "screenshot" in observe:
            observe["screenshot"] = _thin_screenshot(observe.get("screenshot")) or {
                "omitted": True
            }
        if "interact_targets" in observe:
            observe["interact_targets"] = _thin_interact_targets(
                observe.get("interact_targets")
            )
        if "scroll_containers" in observe:
            observe["scroll_containers"] = _thin_scroll_containers(
                observe.get("scroll_containers")
            )
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
    elif "screenshot" in out or "screenshot_ref" in out or "interact_targets" in out:
        out = _thin_result_body(out)
    return out
