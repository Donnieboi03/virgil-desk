"""Tests for desk-events CLI filters."""

from desk_host.events_cli import _summarize_run


def test_summarize_run_counts_screenshots_and_live():
    rows = [
        {"kind": "handoff.decomposed", "flags": {"live": True}, "measure": {"item_count": 3}},
        {"kind": "browser.command_result", "flags": {"has_screenshot": True}},
        {"kind": "browser.command_result", "flags": {"has_screenshot": True}},
        {"kind": "policy.denied", "rule": "screenshot_cap"},
    ]
    summary = _summarize_run(rows)
    assert summary["screenshot_count"] == 2
    assert summary["live_decompose"] is True
    assert summary["item_count"] == 3
    assert summary["kinds"]["policy.denied"] == 1


def test_summarize_run_legacy_top_level_fields():
    rows = [
        {"kind": "handoff.decomposed", "live": True, "item_count": 2},
        {"kind": "browser.command_result", "screenshot_count": 1},
    ]
    summary = _summarize_run(rows)
    assert summary["screenshot_count"] == 1
    assert summary["live_decompose"] is True
    assert summary["item_count"] == 2


def test_summarize_run_omits_live_when_not_reported():
    rows = [
        {"kind": "handoff.decomposed", "measure": {"item_count": 2}},
    ]
    summary = _summarize_run(rows)
    assert summary["live_decompose"] is None
    assert summary["item_count"] == 2


def test_summarize_run_failed_ops():
    rows = [
        {
            "kind": "browser.command_result",
            "flags": {"ok": False, "has_screenshot": False},
            "op": "openTab",
            "error": "timeout",
            "tab_id": 5,
            "url": "https://mail.google.com",
            "command_id": "c1",
        },
        {"kind": "browser.command_result", "flags": {"ok": True, "has_screenshot": True}},
    ]
    summary = _summarize_run(rows)
    assert summary["failed_command_count"] == 1
    assert summary["failed_ops"][0]["op"] == "openTab"
    assert summary["failed_ops"][0]["error"] == "timeout"
    assert summary["failed_ops"][0]["tab_id"] == 5
    assert summary["screenshot_count"] == 1


def test_summarize_run_usage_rollup():
    rows = [
        {
            "kind": "handoff.decomposed",
            "measure": {"item_count": 2, "prompt_tokens": 100, "cost_usd": 0.01},
        },
        {
            "kind": "agent.executed",
            "measure": {
                "browser_ops": 3,
                "prompt_tokens": 200,
                "completion_tokens": 50,
                "total_tokens": 250,
                "cost_usd": 0.05,
            },
        },
        {"kind": "run.finished", "measure": {"cost_usd": 0.05}},
    ]
    summary = _summarize_run(rows)
    assert summary["prompt_tokens"] == 300
    assert summary["completion_tokens"] == 50
    assert summary["total_tokens"] == 250
    assert summary["cost_usd"] == 0.11


def test_summarize_run_omits_usage_when_absent():
    rows = [{"kind": "handoff.decomposed", "measure": {"item_count": 1}}]
    summary = _summarize_run(rows)
    assert "cost_usd" not in summary
    assert "prompt_tokens" not in summary


def test_summarize_run_ext_gap_per_item():
    rows = [
        {
            "kind": "agent.execute_started",
            "item_id": "desk_x_agent_0",
            "ts": "2026-09-09T17:00:00+00:00",
        },
        {
            "kind": "browser.command",
            "op": "observe",
            "ts": "2026-09-09T17:00:01+00:00",
        },
        {
            "kind": "browser.command_result",
            "op": "observe",
            "ts": "2026-09-09T17:00:14+00:00",
            "measure": {
                "duration_ms": 13000,
                "inject_ms": 12000,
                "frame_count": 10,
            },
            "flags": {"ok": True},
        },
        {
            "kind": "browser.command",
            "op": "click",
            "ts": "2026-09-09T17:00:22+00:00",
        },
        {
            "kind": "browser.command_result",
            "op": "click",
            "ts": "2026-09-09T17:00:24+00:00",
            "measure": {"duration_ms": 2000, "inject_ms": 1500},
            "flags": {"ok": True},
        },
        {
            "kind": "agent.executed",
            "item_id": "desk_x_agent_0",
            "ts": "2026-09-09T17:00:30+00:00",
            "measure": {"prompt_tokens": 100, "completion_tokens": 20, "cost_usd": 0.01},
        },
        {
            "kind": "agent.execute_started",
            "item_id": "desk_x_agent_1",
            "ts": "2026-09-09T17:01:00+00:00",
        },
        {
            "kind": "browser.command_result",
            "op": "observe",
            "ts": "2026-09-09T17:01:01+00:00",
            "measure": {"duration_ms": 500},
            "flags": {"ok": True},
        },
        {
            "kind": "agent.executed",
            "item_id": "desk_x_agent_1",
            "ts": "2026-09-09T17:01:03+00:00",
            "measure": {},
        },
    ]
    summary = _summarize_run(rows)
    assert summary["ext_ms_max"] == 15000
    assert summary["ext_ms_min"] == 500
    assert summary["ext_ms_max_item_id"] == "desk_x_agent_0"
    assert len(summary["items"]) == 2
    slow = summary["items"][0]
    assert slow["item_id"] == "desk_x_agent_0"
    assert slow["wall_ms"] == 30000
    assert slow["ext_ms"] == 15000
    assert slow["gap_first_ms"] == 8000  # 14s → 22s command
    assert slow["op_ext"][0]["inject_ms"] == 12000
    assert slow["usage"]["prompt_tokens"] == 100
    fast = summary["items"][1]
    assert fast["ext_ms"] == 500
