"""Unit tests for desk_host.memory."""

from __future__ import annotations

from desk_host.memory import (
    append_notepad_bullet,
    append_recent,
    apply_memory_patch,
    empty_memory,
    format_for_execute,
    seed_run_notepad,
)


def test_append_recent_keeps_last_n():
    mem = empty_memory()
    for i in range(5):
        mem = append_recent(mem, {"item_id": str(i), "summary": f"s{i}"}, recent_max=3)
    assert [e["item_id"] for e in mem["global_recent"]] == ["2", "3", "4"]


def test_seed_and_bullet_trim_chars():
    mem = seed_run_notepad(empty_memory(), "run1", decomposition="triage")
    mem = append_notepad_bullet(
        mem, "run1", "aaaaaaaaaa", max_bullets=10, max_chars=25
    )
    mem = append_notepad_bullet(
        mem, "run1", "bbbbbbbbbb", max_bullets=10, max_chars=25
    )
    mem = append_notepad_bullet(
        mem, "run1", "cccccccccc", max_bullets=10, max_chars=25
    )
    bullets = mem["by_run_id"]["run1"]["bullets"]
    assert sum(len(b) for b in bullets) <= 25
    assert mem["by_run_id"]["run1"]["decomposition"] == "triage"


def test_apply_memory_patch_ops():
    mem = apply_memory_patch(
        empty_memory(),
        [
            {"op": "seed_run", "run_id": "r1", "decomposition": "split"},
            {
                "op": "append_recent",
                "entry": {
                    "item_id": "i1",
                    "title": "t",
                    "outcome": "done",
                    "summary": "ok",
                },
            },
            {"op": "append_bullet", "run_id": "r1", "bullet": "note"},
        ],
        recent_max=3,
    )
    assert mem["by_run_id"]["r1"]["decomposition"] == "split"
    assert len(mem["global_recent"]) == 1
    assert mem["by_run_id"]["r1"]["bullets"] == ["note"]


def test_format_for_execute():
    mem = apply_memory_patch(
        empty_memory(),
        [
            {"op": "seed_run", "run_id": "r1", "decomposition": "d1", "mission": "m"},
            {"op": "append_bullet", "run_id": "r1", "bullet": "b1"},
            {"op": "append_recent", "entry": {"item_id": "x", "summary": "prior"}},
        ],
    )
    fmt = format_for_execute(mem, "r1")
    assert fmt["decomposition"] == "d1"
    assert fmt["run_notepad"]["bullets"] == ["b1"]
    assert fmt["recent_executions"][0]["summary"] == "prior"
