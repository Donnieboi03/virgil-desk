"""Execute concurrency lock helpers."""

from desk_host.app import _executing_item_ids, reset_state_for_tests


def test_executing_item_ids_cleared_on_reset():
    reset_state_for_tests()
    _executing_item_ids.add("item_lock_test")
    assert "item_lock_test" in _executing_item_ids
    reset_state_for_tests()
    assert "item_lock_test" not in _executing_item_ids
