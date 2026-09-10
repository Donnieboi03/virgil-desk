"""Unit tests for desk_host.memory."""

from __future__ import annotations

from desk_host.memory import (
    append_notepad_bullet,
    append_recent,
    apply_memory_patch,
    apply_semantic_patch,
    delete_fact,
    empty_memory,
    empty_semantic,
    format_for_execute,
    seed_run_notepad,
    upsert_fact,
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
    assert "decomposition" not in fmt
    assert fmt["run_notepad"]["decomposition"] == "d1"
    assert fmt["run_notepad"]["bullets"] == ["b1"]
    assert fmt["run_notepad"]["mission"] == "m"
    assert fmt["recent_executions"][0]["summary"] == "prior"
    assert fmt["semantic_facts"] == []


def test_upsert_fact_supersedes_by_key():
    sem = upsert_fact(
        empty_semantic(),
        key="prefer_concise",
        value="Prefer short replies",
        tags=["user"],
        source="manual",
    )
    sem = upsert_fact(
        sem,
        key="prefer_concise",
        value="Prefer very short replies",
        tags=["user"],
        source="host",
    )
    assert len(sem["facts"]) == 1
    assert sem["facts"][0]["value"] == "Prefer very short replies"
    assert sem["facts"][0]["source"] == "host"


def test_delete_fact_and_caps():
    sem = empty_semantic()
    for i in range(5):
        sem = upsert_fact(
            sem,
            key=f"k{i}",
            value=f"v{i}",
            tags=["decision"],
            max_facts=3,
        )
    assert len(sem["facts"]) == 3
    keys = {f["key"] for f in sem["facts"]}
    assert "k4" in keys
    sem = delete_fact(sem, key="k4")
    assert all(f["key"] != "k4" for f in sem["facts"])


def test_apply_semantic_patch_and_format():
    sem = apply_semantic_patch(
        empty_semantic(),
        [
            {
                "op": "upsert_fact",
                "key": "yc_no_false_close",
                "value": "Do not single-closure YC review items",
                "tags": ["decision"],
            },
            {
                "op": "upsert_fact",
                "key": "prefer_concise",
                "value": "Be concise",
                "tags": ["user"],
            },
        ],
    )
    fmt = format_for_execute(empty_memory(), "r1", semantic=sem, packet_max_facts=1)
    assert len(fmt["semantic_facts"]) == 1
    assert "key" in fmt["semantic_facts"][0]
    assert "value" in fmt["semantic_facts"][0]


def test_semantic_value_and_key_truncation():
    sem = upsert_fact(
        empty_semantic(),
        key="k" * 100,
        value="v" * 500,
        max_key_chars=64,
        max_value_chars=200,
    )
    assert len(sem["facts"][0]["key"]) == 64
    assert len(sem["facts"][0]["value"]) == 200
    fmt = format_for_execute(
        empty_memory(),
        "r1",
        semantic=sem,
        max_key_chars=32,
        max_value_chars=50,
    )
    assert fmt["semantic_facts"][0]["key"] == ("k" * 32)
    assert fmt["semantic_facts"][0]["value"] == ("v" * 50)


def test_empty_semantic_always_list():
    fmt = format_for_execute(empty_memory(), "missing-run", semantic=None)
    assert fmt["semantic_facts"] == []
    fmt2 = format_for_execute(empty_memory(), "missing-run", semantic=empty_semantic())
    assert fmt2["semantic_facts"] == []
