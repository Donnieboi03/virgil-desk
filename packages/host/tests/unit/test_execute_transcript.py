"""Unit tests for Host execute transcript prune."""

from __future__ import annotations

import json

from desk_host.execute_transcript import prune_messages, stub_eyes_tool_content


def _eyes_tool(i: int) -> dict:
    return {
        "role": "tool",
        "tool_call_id": f"c{i}",
        "name": "observe",
        "content": json.dumps(
            {
                "ok": True,
                "op": "observe",
                "result": {
                    "ok": True,
                    "url": f"https://example.com/{i}",
                    "interact_targets": [{"id": i, "label": f"row{i}"}],
                    "scrape_excerpt": "x" * 200,
                },
            }
        ),
    }


def test_prune_keeps_last_n_full_and_stubs_older():
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "user",
            "content": '## Task\n\n```json\n{"item":{"hints":{"members":[{"sender":"A"}]}}}\n```',
        },
        _eyes_tool(0),
        _eyes_tool(1),
        _eyes_tool(2),
    ]
    out = prune_messages(messages, eyes_keep_last=2)
    assert out[0]["content"] == "sys"
    assert "members" in out[1]["content"]
    stub0 = json.loads(out[2]["content"])
    assert stub0.get("stub") is True or (stub0.get("result") or {}).get("stub") is True
    assert "eyes_pruned" in json.dumps(stub0)
    full1 = json.loads(out[3]["content"])
    full2 = json.loads(out[4]["content"])
    assert "interact_targets" in (full1.get("result") or full1)
    assert "interact_targets" in (full2.get("result") or full2)


def test_prune_keep_zero_stubs_all_tools():
    messages = [{"role": "system", "content": "s"}, _eyes_tool(0), _eyes_tool(1)]
    out = prune_messages(messages, eyes_keep_last=0)
    for m in out[1:]:
        body = json.loads(m["content"])
        assert body.get("stub") is True or "eyes_pruned" in json.dumps(body)


def test_stub_eyes_preserves_error():
    raw = {"ok": False, "op": "click", "result": {"ok": False, "error": "stale_observe", "url": "https://x"}}
    stub = json.loads(stub_eyes_tool_content(raw))
    assert stub["stub"] is True
    assert stub["error"] == "stale_observe"
