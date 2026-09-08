"""Execute summary failure detection."""

from desk_host.execute_validation import (
    execute_summary_indicates_failure,
    strip_max_iter_banner,
)


def test_detects_timeout_denying_command():
    text = "⏱ Timeout — denying command\nI am unable to proceed with the requested browser action."
    assert execute_summary_indicates_failure(text)


def test_detects_policy_blocked():
    assert execute_summary_indicates_failure("blocked due to user policy restrictions")


def test_detects_partial_not_max_iterations():
    assert not execute_summary_indicates_failure("Reached maximum iterations")
    assert not execute_summary_indicates_failure(
        "⚠️  Reached maximum iterations (20). Requesting summary...\n"
        "Reviewed Engevity August 2026 Monthly Update from Deilen Davis."
    )
    assert execute_summary_indicates_failure(
        "Partial: searched inbox but could not open thread"
    )


def test_strip_max_iter_banner():
    raw = (
        "⚠️  Reached maximum iterations (20). Requesting summary...\n"
        "Reviewed Engevity August 2026 Monthly Update from Deilen Davis."
    )
    assert strip_max_iter_banner(raw) == (
        "Reviewed Engevity August 2026 Monthly Update from Deilen Davis."
    )


def test_accepts_normal_summary():
    assert not execute_summary_indicates_failure(
        "Reviewed inbox scrape; Cursor payment email visible."
    )
