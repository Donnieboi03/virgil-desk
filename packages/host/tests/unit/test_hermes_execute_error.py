"""HermesExecuteError carries pipes + usage for empty-stdout obs."""

import pytest

from desk_host.backends.hermes import HermesBackend, HermesExecuteError, HermesRunResult
from desk_host.config import load_config
from desk_host.observability import read_events, site_fingerprint


def test_hermes_execute_error_carries_pipes_and_usage():
    result = HermesRunResult(
        stdout="DESK_USAGE:{}",
        stderr="trace",
        exit_code=0,
        usage={"prompt_tokens": 10, "cost_usd": 0.01},
    )
    err = HermesExecuteError(
        "hermes execute returned empty output",
        result=result,
        empty_output=True,
    )
    assert err.empty_output is True
    assert err.stdout == "DESK_USAGE:{}"
    assert err.stderr == "trace"
    assert err.exit_code == 0
    assert err.usage == {"prompt_tokens": 10, "cost_usd": 0.01}


def test_site_fingerprint_host_and_first_path():
    assert site_fingerprint("https://mail.google.com/mail/u/0/#inbox") == "mail.google.com/mail"
    assert site_fingerprint("https://example.com/") == "example.com"
    assert site_fingerprint("") is None
    assert site_fingerprint(None) is None


@pytest.mark.asyncio
async def test_execute_item_nonzero_exit_raises_hermes_execute_error(monkeypatch):
    async def fake_scrape(*_a, **_k):
        return {"ok": True, "url": "https://example.com", "title": "t", "scrape_excerpt": "x"}

    async def fake_run(self, message, **kwargs):
        return HermesRunResult(
            stdout="",
            stderr="boom",
            exit_code=1,
            usage={"prompt_tokens": 3, "cost_usd": 0.001},
        )

    monkeypatch.setattr("desk_host.app.dispatch_browser_command_and_wait", fake_scrape)
    monkeypatch.setattr(HermesBackend, "_hermes_run", fake_run)
    monkeypatch.setenv("DESK_AGENT_BACKEND", "hermes")
    backend = HermesBackend()
    with pytest.raises(HermesExecuteError) as ei:
        await backend.execute_item(
            {"id": "i1", "title": "t", "column": "agent"},
            {
                "run_id": "desk_nonzero",
                "human_tab_id": 1,
                "agent_tab_id": 2,
                "handoff_url": "https://example.com",
            },
        )
    err = ei.value
    assert err.empty_output is False
    assert err.exit_code == 1
    assert err.usage["prompt_tokens"] == 3
    assert err.stderr == "boom"


@pytest.mark.asyncio
async def test_record_execute_failed_includes_snippets(tmp_path, monkeypatch):
    from desk_host.app import _record_execute_failed_event, reset_config_cache, reset_state_for_tests

    monkeypatch.setenv("DESK_LOG_DIR", str(tmp_path / "logs"))
    reset_config_cache()
    reset_state_for_tests()
    load_config()
    exc = HermesExecuteError(
        "hermes execute returned empty output",
        result=HermesRunResult(
            stdout="partial model text",
            stderr="warn",
            exit_code=0,
            usage={"prompt_tokens": 42, "cost_usd": 0.03},
        ),
        empty_output=True,
    )
    _record_execute_failed_event(
        run_id="desk_fail_snip",
        item_id="desk_fail_snip_agent_0",
        err=str(exc),
        exc=exc,
        outcome="empty_output",
    )
    rows = read_events(run_id="desk_fail_snip")
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "agent.execute_failed"
    assert row["flags"]["empty_output"] is True
    assert row["flags"]["outcome"] == "empty_output"
    assert row["stdout_snippet"] == "partial model text"
    assert row["stderr_snippet"] == "warn"
    assert row["measure"]["exit_code"] == 0
    assert row["measure"]["prompt_tokens"] == 42
    assert row["measure"]["cost_usd"] == 0.03
