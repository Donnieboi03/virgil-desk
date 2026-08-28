"""Hermes CLI invocation tests."""

import pytest

from desk_host.backends.hermes import HermesBackend, HermesRunResult


@pytest.mark.asyncio
async def test_hermes_run_uses_chat_query_flags(monkeypatch):
    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        class Proc:
            stdout = '{"decomposition":"ok","items":[]}'
            stderr = ""
            returncode = 0

        return Proc()

    monkeypatch.setattr("desk_host.backends.hermes.subprocess.run", fake_run)
    backend = HermesBackend()
    result = await backend._hermes_run("test prompt")
    assert isinstance(result, HermesRunResult)
    assert "-Q" in captured["args"]
    assert "-q" in captured["args"]
    assert "test prompt" in captured["args"]
    assert "--json" not in captured["args"]
    assert "--source" in captured["args"]
