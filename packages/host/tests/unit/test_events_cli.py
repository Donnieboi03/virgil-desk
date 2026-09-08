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
