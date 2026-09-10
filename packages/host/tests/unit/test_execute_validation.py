"""Execute summary failure detection."""

from desk_host.execute_validation import (
    empty_probe_links_only_cover,
    execute_summary_incomplete_reason,
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
        "Reviewed August 2026 Monthly Update from the sender."
    )
    assert execute_summary_indicates_failure(
        "Partial: searched inbox but could not open thread"
    )


def test_strip_max_iter_banner():
    raw = (
        "⚠️  Reached maximum iterations (20). Requesting summary...\n"
        "Reviewed August 2026 Monthly Update from the sender."
    )
    assert strip_max_iter_banner(raw) == (
        "Reviewed August 2026 Monthly Update from the sender."
    )


def test_accepts_normal_summary():
    assert not execute_summary_indicates_failure(
        "Reviewed inbox scrape; Cursor payment email visible."
    )
    assert execute_summary_incomplete_reason(
        "Reviewed inbox scrape; Cursor payment email visible."
    ) is None


def test_open_only_observed_is_incomplete():
    reason = execute_summary_incomplete_reason(
        "Observed PandaDoc notification confirming the agreement was completed."
    )
    assert reason and "open-only" in reason


def test_opened_summary_incomplete_unless_single_closure():
    assert execute_summary_incomplete_reason(
        "Opened Job Board round-up email featuring Acme."
    )
    assert (
        execute_summary_incomplete_reason(
            "Single closure: extracted Acme rate from Job Board email; no further action."
        )
        is None
    )


def test_verified_terminal_opened_summary_is_done():
    """Review goals that verify expired/submitted pages are Completed, not park."""
    assert (
        execute_summary_incomplete_reason(
            "Opened Example Corp update email; screening questionnaire link "
            "redirected to expired-or-not-found (deadline has passed or already "
            "submitted); verified expired; no further action."
        )
        is None
    )
    assert (
        execute_summary_incomplete_reason(
            "Verified expired screening link (7-day deadline passed / already submitted)."
        )
        is None
    )
    assert (
        execute_summary_incomplete_reason(
            "Followed the screening questionnaire link; already submitted; review complete."
        )
        is None
    )


def test_opened_with_park_to_you_column_is_done():
    """Open-only gate must not false-fail real park language after 'Opened…'."""
    summary = (
        "Opened August 2026 Monthly Update from the sender; "
        "parked Drive folder and PandaDoc agreement to You column."
    )
    assert execute_summary_incomplete_reason(summary) is None
    assert execute_summary_incomplete_reason(
        "Opened thread; parked human review subtasks for Drive + job link."
    ) is None
    assert execute_summary_incomplete_reason(
        "Opened thread; parked remainder You for auth wall."
    ) is None


def test_partial_not_flagged_incomplete():
    assert (
        execute_summary_incomplete_reason("Partial: could not open Drive link") is None
    )


def test_failed_open_tab_blocks_reviewed():
    from desk_host.execute_validation import failed_open_tab_blocks_done

    assert failed_open_tab_blocks_done(
        failed_ops=["openTab"],
        summary="Reviewed Gmail inbox for payment emails.",
    )
    assert failed_open_tab_blocks_done(
        failed_ops=["openTab"],
        summary="Finished extracting the deadline from the thread.",
    )
    assert (
        failed_open_tab_blocks_done(
            failed_ops=["openTab"],
            summary="Partial: openTab failed; parked You with draft keywords",
        )
        is None
    )
    assert (
        failed_open_tab_blocks_done(
            failed_ops=["openTab"],
            summary="Remainder parked for human with LinkedIn draft checklist.",
        )
        is None
    )
    assert (
        failed_open_tab_blocks_done(
            failed_ops=["click"],
            summary="Reviewed thread body; Single closure: extracted deadline.",
        )
        is None
    )


def test_empty_probe_links_only_cover():
    assert empty_probe_links_only_cover(
        ops_since_start=["scrape", "observe", "click", "observe", "probe_links"],
        last_probe_links_empty=True,
    )
    assert (
        empty_probe_links_only_cover(
            ops_since_start=["scrape", "observe", "click", "observe", "probe_links"],
            last_probe_links_empty=False,
        )
        is None
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


def test_auth_gate_blocks_false_closure():
    from desk_host.execute_validation import auth_gate_blocks_false_closure

    assert auth_gate_blocks_false_closure(
        "Single closure: reviewed monthly update; no further action.",
        has_auth_gate_you=True,
    )
    assert (
        auth_gate_blocks_false_closure(
            "Verified Drive summary; remainder parked You for human glance.",
            has_auth_gate_you=True,
        )
        is None
    )
    assert (
        auth_gate_blocks_false_closure(
            "Single closure: done.",
            has_auth_gate_you=False,
        )
        is None
    )


def test_human_judgment_blocks_false_closure():
    from desk_host.execute_validation import human_judgment_blocks_false_closure

    # YC-style: Review title + read-only single closure → reject
    assert human_judgment_blocks_false_closure(
        "Single closure: Reviewed YC Co-Founder Match picks; no further action.",
        item_title="Review YC Co-Founder Match profile picks",
    )
    # Access folder + verified access sold as done → reject
    assert human_judgment_blocks_false_closure(
        "Single closure: verified access to Google Drive shared folder; no further action.",
        item_title="Access shared folder 'Team 1:1 Notes'",
    )
    # Summary-only "Reviewed" + single closure even without title verb → reject
    assert human_judgment_blocks_false_closure(
        "Single closure: Reviewed two candidate profiles; no further action.",
        item_title="Open co-founder email",
    )
    # Verified terminal still OK (employer screening expired)
    assert (
        human_judgment_blocks_false_closure(
            "Verified expired link (deadline passed / already submitted) for "
            "Example Corp screening; no further action.",
            item_title="Respond to Example Corp application inquiry",
        )
        is None
    )
    # Honest remainder park OK
    assert (
        human_judgment_blocks_false_closure(
            "Opened profiles; remainder parked You for decide on Candidate A / Candidate B.",
            item_title="Review YC Co-Founder Match profile picks",
        )
        is None
    )
    # Already has You remainder → defer to auth_gate_blocks honesty gate
    assert (
        human_judgment_blocks_false_closure(
            "Single closure: Reviewed picks; no further action.",
            item_title="Review YC picks",
            has_you_remainder=True,
        )
        is None
    )
    # Factual extract without review/access language OK
    assert (
        human_judgment_blocks_false_closure(
            "Single closure: extracted Acme rate from Job Board email; no further action.",
            item_title="Check Acme rate in Job Board round-up",
        )
        is None
    )


def test_open_you_remainder_kinds():
    from desk_host.execute_validation import open_auth_gate_you, open_you_remainder

    items = {
        "y1": {
            "id": "y1",
            "parent_id": "p1",
            "column": "you",
            "status": "proposed",
            "park_kind": "human_remainder",
        }
    }
    assert open_auth_gate_you("p1", items) is None
    assert open_you_remainder("p1", items) and open_you_remainder("p1", items)["id"] == "y1"
    items["y1"]["park_kind"] = "auth_gate"
    assert open_auth_gate_you("p1", items)["id"] == "y1"
