"""General observability record envelope tests."""

from dataclasses import replace

from desk_host.config import load_config
from desk_host.observability import limits_from_config, measure_from_snapshot, record, read_events


def test_measure_from_snapshot_extracts_capture_facts():
    cfg = load_config()
    excerpt_len = min(8000, cfg.browser.handoff_excerpt_max_chars)
    snap = {
        "excerpt": "x" * excerpt_len,
        "links": ["https://a.com"] * 50,
        "capture": {
            "scroll_loops_executed": cfg.browser.handoff_scroll_loops,
            "scroll_loops_configured": cfg.browser.handoff_scroll_loops,
            "scrape_text_chars": 12000,
            "excerpt_chars": excerpt_len,
            "full_text_chars": 25000,
            "full_link_count": 300,
            "link_count": 50,
            "scrape_text_capped": True,
            "handoff_excerpt_capped": True,
            "links_capped": True,
        },
    }
    measure, flags = measure_from_snapshot(snap)
    assert measure["full_text_chars"] == 25000
    assert measure["scroll_loops_executed"] == cfg.browser.handoff_scroll_loops
    assert flags["scrape_text_capped"] is True
    assert flags["handoff_excerpt_capped"] is True
    assert flags["links_capped"] is True


def test_limits_from_config_includes_prompts():
    cfg = load_config()
    limits = limits_from_config(cfg)
    assert limits["prompts"]["decompose_items_max"] == cfg.prompts.decompose_items_max
    assert "browser" in limits
    assert "hermes" in limits
    assert limits["memory"]["semantic_max_facts"] == cfg.memory.semantic_max_facts
    assert limits["memory"]["recent_max"] == cfg.memory.recent_max


def test_usage_measure_keeps_numeric_fields_only():
    from desk_host.observability import usage_measure

    assert usage_measure(None) == {}
    assert usage_measure({}) == {}
    assert usage_measure({"prompt_tokens": 10, "junk": "x", "cost_usd": "0.12"}) == {
        "prompt_tokens": 10,
        "cost_usd": 0.12,
    }
    assert usage_measure({"cost_usd": "n/a"}) == {}


def test_record_emits_envelope(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("DESK_LOG_DIR", str(log_dir))
    cfg = load_config()
    record(
        "handoff.decomposed",
        "desk_test",
        cfg=cfg,
        measure={"item_count": 3},
        flags={"live": True},
        backend="mock",
    )
    rows = read_events(run_id="desk_test")
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "handoff.decomposed"
    assert row["measure"]["item_count"] == 3
    assert row["flags"]["live"] is True
    assert row["limits"]["prompts"]["decompose_items_max"] == cfg.prompts.decompose_items_max
    assert row["backend"] == "mock"


def test_browser_command_result_fields_includes_error_tab_url():
    from desk_host.observability import browser_command_result_fields

    fields = browser_command_result_fields(
        {
            "command_id": "c1",
            "ok": False,
            "error": "inject failed",
            "tab_id": 9,
            "url": "https://linkedin.com/x",
            "duration_ms": 12,
            "scrape_excerpt": "",
            "interact_targets": [],
            "op": "scrape",
        },
        op="scrape",
        screenshot_count_run_total=3,
    )
    assert fields["flags"]["ok"] is False
    assert fields["detail"]["error"] == "inject failed"
    assert fields["detail"]["tab_id"] == 9
    assert fields["detail"]["url"] == "https://linkedin.com/x"
    assert fields["detail"]["op"] == "scrape"
    assert fields["measure"]["screenshot_count_run_total"] == 3


def test_browser_command_result_fields_eyes_settle():
    from desk_host.observability import browser_command_result_fields

    fields = browser_command_result_fields(
        {
            "command_id": "c2",
            "ok": True,
            "op": "observe",
            "scrape_excerpt": "",
            "interact_targets": [],
            "eyes_empty": True,
            "eyes_settle_ms": 1800,
            "eyes_settle_attempts": 8,
            "inject_ms": 12000,
            "frame_count": 14,
            "challenge_extended": False,
            "duration_ms": 1900,
        },
        op="observe",
    )
    assert fields["flags"]["eyes_empty"] is True
    assert fields["flags"]["challenge_extended"] is False
    assert fields["measure"]["eyes_settle_ms"] == 1800
    assert fields["measure"]["eyes_settle_attempts"] == 8
    assert fields["measure"]["inject_ms"] == 12000
    assert fields["measure"]["frame_count"] == 14


def test_browser_command_result_fields_eyes_mode():
    from desk_host.observability import browser_command_result_fields

    fields = browser_command_result_fields(
        {
            "command_id": "c3",
            "ok": True,
            "op": "observe",
            "scrape_excerpt": "",
            "interact_targets": [],
            "eyes_empty": True,
            "eyes_mode": 2,
            "eyes_hints": {"url_path_hint": "expired_or_stale"},
            "eyes_settle_ms": 2006,
            "eyes_settle_attempts": 9,
            "challenge_extended": True,
            "duration_ms": 2100,
        },
        op="observe",
    )
    assert fields["flags"]["eyes_empty"] is True
    assert fields["flags"]["eyes_mode"] == 2
    assert fields["flags"]["challenge_extended"] is True
    assert fields["detail"]["eyes_hints"] == {"url_path_hint": "expired_or_stale"}
    assert fields["measure"]["eyes_settle_ms"] == 2006


def test_limits_reflect_cfg_override():
    cfg = load_config()
    cfg = replace(cfg, prompts=replace(cfg.prompts, decompose_items_max=7))
    limits = limits_from_config(cfg)
    assert limits["prompts"]["decompose_items_max"] == 7
