"""Unit tests for harness on everyday Chrome backend (no live Chrome)."""

from __future__ import annotations

import json

import pytest

from desk_host import harness_backend as hb


@pytest.fixture(autouse=True)
def _reset():
    hb.reset_for_tests()
    yield
    hb.reset_for_tests()


def test_build_ensure_script_uses_python_none_not_json_null():
    script = hb.build_ensure_target_script(seed_url="https://example.com/", existing_target_id=None)
    assert "existing = None" in script
    assert "existing = null" not in script


def test_build_op_script_none_shot_path_is_python_none():
    script = hb.build_op_script(
        "observe",
        {},
        target_id="T1",
        screenshot_path=None,
        skip_screenshot=True,
        excerpt_max=100,
    )
    assert "shot_path = None" in script
    assert "shot_path = null" not in script
    assert "json.loads" in script


def test_map_connection_error_allow_debugging():
    msg = hb.map_connection_error("please Allow remote debugging for this browser")
    assert "chrome://inspect" in msg
    assert "Allow" in msg


def test_strip_virgil_cdp_env():
    env = {
        "BU_CDP_URL": "http://127.0.0.1:9223",
        "BU_NAME": "other",
        "PATH": "/usr/bin",
    }
    out = hb._strip_virgil_cdp_env(env)
    assert "BU_CDP_URL" not in out
    assert out["PATH"] == "/usr/bin"


def test_build_op_script_embeds_click_xy():
    script = hb.build_op_script(
        "click",
        {"x": 10, "y": 20},
        target_id="T1",
        screenshot_path=None,
        skip_screenshot=True,
        excerpt_max=100,
    )
    assert '"click"' in script or "'click'" in script or "click" in script
    assert "click_at_xy" in script
    assert "10" in script and "20" in script


def test_run_browser_op_sticky_target_with_fake_script(monkeypatch):
    calls: list[str] = []

    def fake_run(source, *, harness_bin, bu_name, timeout_sec):
        calls.append(source)
        assert bu_name == "virgil-desk"
        assert harness_bin == "browser-harness"
        if "opened_by_harness" in source and "new_tab" in source:
            return json.dumps(
                {
                    "ok": True,
                    "target_id": "TID_ABC",
                    "opened_by_harness": True,
                    "url": "https://example.com/inbox",
                    "title": "Inbox",
                }
            )
        # op script
        return json.dumps(
            {
                "ok": True,
                "url": "https://example.com/inbox",
                "title": "Inbox",
                "scrape_excerpt": "hello",
                "text_omitted": False,
                "eyes": "harness",
                "driver": "harness",
                "interact_targets": [],
                "scroll_containers": [],
                "viewport": {"w": 800, "h": 600},
                "device_pixel_ratio": 2,
                "act_resolved": {
                    "op": "click",
                    "requested": {"x": 1, "y": 2},
                    "used": "xy",
                    "url_before": "https://example.com/inbox",
                    "url_after": "https://example.com/inbox#t",
                },
            }
        )

    hb.set_run_script_override(fake_run)
    result = hb.run_browser_op(
        {
            "run_id": "desk_h1",
            "command_id": "c1",
            "op": "click",
            "handoff_url": "https://example.com/inbox",
            "params": {"x": 1, "y": 2},
            "skip_screenshot": True,
        },
        harness_bin="browser-harness",
        bu_name="virgil-desk",
        skip_screenshot=True,
    )
    assert result["ok"] is True
    assert result["driver"] == "harness"
    assert result["act_resolved"]["used"] == "xy"
    sticky = hb._sessions.get("desk_h1")
    assert sticky is not None
    assert sticky.target_id == "TID_ABC"
    assert sticky.opened_by_harness is True
    assert len(calls) == 2

    # Second op reuses sticky target
    result2 = hb.run_browser_op(
        {
            "run_id": "desk_h1",
            "command_id": "c2",
            "op": "observe",
            "handoff_url": "https://example.com/inbox",
            "params": {},
            "skip_screenshot": True,
        },
        harness_bin="browser-harness",
        bu_name="virgil-desk",
        skip_screenshot=True,
    )
    assert result2["ok"] is True
    assert "TID_ABC" in calls[2]  # ensure script received existing id


def test_click_without_coords_fails_used_none():
    def fake_run(source, *, harness_bin, bu_name, timeout_sec):
        if "opened_by_harness" in source and "list_tabs" in source:
            return json.dumps(
                {
                    "ok": True,
                    "target_id": "T",
                    "opened_by_harness": False,
                    "url": "https://example.com/",
                    "title": "x",
                }
            )
        return json.dumps(
            {
                "ok": False,
                "url": "https://example.com/",
                "title": "x",
                "scrape_excerpt": "",
                "interact_targets": [],
                "act_resolved": {
                    "op": "click",
                    "requested": {"target_id": 7},
                    "used": "none",
                    "url_before": "https://example.com/",
                    "url_after": "https://example.com/",
                    "error": "click requires x/y or selector",
                },
                "error": "click requires x/y or selector",
            }
        )

    hb.set_run_script_override(fake_run)
    result = hb.run_browser_op(
        {
            "run_id": "desk_miss",
            "command_id": "c1",
            "op": "click",
            "handoff_url": "https://example.com/",
            "params": {"target_id": 7},
            "skip_screenshot": True,
        },
        harness_bin="browser-harness",
        bu_name="virgil-desk",
        skip_screenshot=True,
    )
    assert result["ok"] is False
    assert result["act_resolved"]["used"] == "none"


@pytest.mark.asyncio
async def test_dispatch_harness_records_driver(monkeypatch):
    monkeypatch.setenv("DESK_BROWSER_DRIVER", "harness")
    from desk_host.config import clear_config_cache, load_config
    from desk_host.app import (
        dispatch_browser_command_and_wait,
        get_config,
        reset_state_for_tests,
    )

    clear_config_cache()
    reset_state_for_tests()
    cfg = load_config()
    assert cfg.browser.driver == "harness"
    monkeypatch.setattr("desk_host.app.get_config", lambda: cfg)

    def fake_run(source, *, harness_bin, bu_name, timeout_sec):
        if "list_tabs" in source or "new_tab" in source:
            return json.dumps(
                {
                    "ok": True,
                    "target_id": "T9",
                    "opened_by_harness": False,
                    "url": "https://example.com/",
                    "title": "Ex",
                }
            )
        return json.dumps(
            {
                "ok": True,
                "url": "https://example.com/",
                "title": "Ex",
                "scrape_excerpt": "body",
                "interact_targets": [],
                "eyes": "harness",
                "driver": "harness",
            }
        )

    hb.set_run_script_override(fake_run)
    result = await dispatch_browser_command_and_wait(
        {
            "run_id": "desk_dispatch",
            "op": "observe",
            "handoff_url": "https://example.com/",
            "tab_id": 2,
            "human_tab_id": 1,
            "params": {},
            "skip_screenshot": True,
        },
        timeout=5.0,
    )
    assert result["driver"] == "harness"
    assert result["ok"] is True
    reset_state_for_tests()
