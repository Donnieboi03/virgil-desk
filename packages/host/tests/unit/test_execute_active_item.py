"""Active-item map + per-run execute lock (mine-ready obs)."""

from desk_host.app import (
    _active_item_by_run,
    _execute_session_end,
    _executing_item_ids,
    _executing_run_ids,
    _op_seq_by_key,
    reset_state_for_tests,
)


def test_executing_maps_cleared_on_reset():
    reset_state_for_tests()
    _executing_item_ids.add("item_a")
    _executing_run_ids["desk_r"] = "item_a"
    _active_item_by_run["desk_r"] = "item_a"
    reset_state_for_tests()
    assert "item_a" not in _executing_item_ids
    assert "desk_r" not in _executing_run_ids
    assert "desk_r" not in _active_item_by_run


def test_execute_session_end_only_clears_matching_active_item():
    reset_state_for_tests()
    run_id = "desk_overlap"
    _active_item_by_run[run_id] = "item_b"
    _op_seq_by_key[(run_id, "item_a")] = 3
    _op_seq_by_key[(run_id, "item_b")] = 1

    # Ending item_a must not wipe item_b's active stamp.
    _execute_session_end(run_id, "item_a")
    assert _active_item_by_run[run_id] == "item_b"
    assert (run_id, "item_a") not in _op_seq_by_key
    assert _op_seq_by_key[(run_id, "item_b")] == 1

    _execute_session_end(run_id, "item_b")
    assert run_id not in _active_item_by_run
    assert (run_id, "item_b") not in _op_seq_by_key
