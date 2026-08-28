"""Hermes CLI invocation tests."""

import tempfile
from pathlib import Path

import pytest

from desk_host.backends.hermes import HermesBackend, HermesRunResult, build_decompose_prompt


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


@pytest.mark.asyncio
async def test_hermes_run_passes_image_flag(monkeypatch):
    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args

        class Proc:
            stdout = "ok"
            stderr = ""
            returncode = 0

        return Proc()

    monkeypatch.setattr("desk_host.backends.hermes.subprocess.run", fake_run)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(b"\x89PNG\r\n")
        path = tmp.name
    backend = HermesBackend()
    await backend._hermes_run("vision prompt", image_path=path)
    assert "--image" in captured["args"]
    assert path in captured["args"]


def test_build_decompose_prompt_strips_screenshot_blob():
    handoff = {
        "url": "https://example.com",
        "title": "Example",
        "snapshot": {
            "excerpt": "hello",
            "links": ["https://example.com/a"],
            "screenshot": {"mime": "image/png", "base64": "abc"},
        },
    }
    prompt = build_decompose_prompt(handoff)
    assert "hello" in prompt
    assert "abc" not in prompt
