"""Tests for decompose_parser."""

import json

from desk_host.decompose_parser import parse_decompose_json


def test_parse_clean_json():
    raw = json.dumps(
        {
            "decomposition": "Research the job; you apply when ready.",
            "items": [
                {"column": "agent", "title": "Read listing", "status": "running"},
                {"column": "you", "title": "Submit application", "status": "proposed"},
            ],
        }
    )
    out = parse_decompose_json(raw, "desk_abc", {"url": "https://example.com", "human_tab_id": 1})
    assert out is not None
    assert len(out["items"]) == 2
    assert out["items"][0]["id"] == "desk_abc_agent_0"
    assert out["items"][0]["run_id"] == "desk_abc"
    assert out["items"][0]["status"] == "proposed"


def test_agent_done_coerced_to_proposed_and_hints_kept():
    raw = json.dumps(
        {
            "decomposition": "Triage inbox.",
            "items": [
                {
                    "column": "agent",
                    "title": "Review GitHub permissions",
                    "status": "done",
                    "hints": {
                        "search_query": "GitHub Cursor permissions",
                        "sender": "GitHub",
                        "subject_contains": "updated permissions",
                    },
                }
            ],
        }
    )
    out = parse_decompose_json(
        raw, "desk_hint", {"url": "https://mail.google.com", "human_tab_id": 1}
    )
    assert out is not None
    agent = out["items"][0]
    assert agent["status"] == "proposed"
    assert agent["hints"]["search_query"] == "GitHub Cursor permissions"
    assert agent["hints"]["sender"] == "GitHub"


def test_parse_markdown_wrapped():
    raw = 'Here:\n```json\n{"decomposition":"x","items":[{"column":"waiting","title":"Slot","proposals":[{"kind":"calendar_slot","payload":{"start":"t"}}]}]}\n```'
    out = parse_decompose_json(raw, "desk_x", {"url": "https://a.com"})
    assert out is not None
    assert out["items"][0]["column"] == "waiting"


def test_parse_malformed_returns_none():
    assert parse_decompose_json("not json", "desk_x", {}) is None
    assert parse_decompose_json('{"items":[]}', "desk_x", {}) is None


def test_parse_truncates_items_above_config_max(monkeypatch):
    items = [{"column": "agent", "title": f"T{i}", "status": "proposed"} for i in range(8)]
    raw = json.dumps({"decomposition": "many", "items": items})

    class FakePrompts:
        decompose_items_max = 5
        work_item_title_max_chars = 200

    class FakeCfg:
        prompts = FakePrompts()

    monkeypatch.setattr("desk_host.decompose_parser.load_config", lambda: FakeCfg())
    out = parse_decompose_json(raw, "desk_cap", {"url": "https://example.com"})
    assert out is not None
    assert len(out["items"]) == 5
