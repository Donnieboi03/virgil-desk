"""Tests for desk-events CLI filters."""

import json

from desk_host.events_cli import _summarize_run


def test_summarize_run_counts_screenshots_and_live():
    rows = [
        {"kind": "handoff.decomposed", "live": True},
        {"kind": "browser.command_result", "screenshot_count": 1},
        {"kind": "browser.command_result", "screenshot_count": 1},
        {"kind": "policy.denied", "rule": "screenshot_cap"},
    ]
    summary = _summarize_run(rows)
    assert summary["screenshot_count"] == 2
    assert summary["live_decompose"] is True
    assert summary["kinds"]["policy.denied"] == 1
