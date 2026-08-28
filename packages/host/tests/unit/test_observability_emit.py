"""emit() must not let payload fields overwrite event kind."""

from desk_host.observability import emit, read_events


def test_emit_kind_not_overwritten_by_fields(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("DESK_LOG_DIR", str(log_dir))
    emit(
        "proposal.accepted",
        "desk_test",
        {"proposal_id": "p1", "proposal_kind": "calendar_slot"},
    )
    rows = read_events(run_id="desk_test")
    assert len(rows) == 1
    assert rows[0]["kind"] == "proposal.accepted"
    assert rows[0]["proposal_kind"] == "calendar_slot"
