"""Execute summary failure detection."""

from desk_host.execute_validation import (
    execute_summary_indicates_failure,
    open_agent_children,
    parent_done_blocked_reason,
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


def test_parent_done_blocked_with_open_agent_children():
    items = {
        "p1": {"id": "p1", "column": "agent", "status": "running", "kind": "parent"},
        "c1": {
            "id": "c1",
            "column": "agent",
            "status": "proposed",
            "parent_id": "p1",
            "kind": "subtask",
            "title": "Follow Drive link",
        },
        "y1": {
            "id": "y1",
            "column": "you",
            "status": "proposed",
            "parent_id": "p1",
            "kind": "subtask",
            "title": "Approve invite",
        },
    }
    assert len(open_agent_children("p1", items)) == 1
    reason = parent_done_blocked_reason(items["p1"], items)
    assert reason and "Follow Drive link" in reason
    assert parent_done_blocked_reason(items["c1"], items) is None


def test_parent_done_ok_when_children_done():
    items = {
        "p1": {"id": "p1", "column": "agent", "status": "running"},
        "c1": {
            "id": "c1",
            "column": "agent",
            "status": "done",
            "parent_id": "p1",
            "title": "Done child",
        },
    }
    assert parent_done_blocked_reason(items["p1"], items) is None
