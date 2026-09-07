"""Execute summary failure detection."""

from desk_host.execute_validation import execute_summary_indicates_failure


def test_detects_timeout_denying_command():
    text = "⏱ Timeout — denying command\nI am unable to proceed with the requested browser action."
    assert execute_summary_indicates_failure(text)


def test_detects_policy_blocked():
    assert execute_summary_indicates_failure("blocked due to user policy restrictions")


def test_detects_max_iterations_and_partial():
    assert execute_summary_indicates_failure("Reached maximum iterations")
    assert execute_summary_indicates_failure("Partial: searched inbox but could not open thread")


def test_accepts_normal_summary():
    assert not execute_summary_indicates_failure("Reviewed inbox scrape; Cursor payment email visible.")
