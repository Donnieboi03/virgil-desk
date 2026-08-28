"""Unit tests for mock extension observe payloads."""

from helpers.mock_extension import fake_command_result


def test_fake_observe_has_interact_targets():
    result = fake_command_result("cmd1", op="observe")
    assert result["interact_targets"][0]["ref"] == "t1"
    assert result["observe"]["viewport"]["w"] == 1280


def test_fake_click_has_act_resolved():
    result = fake_command_result("cmd2", op="click")
    assert result["act_resolved"]["used"] == "target_id"
