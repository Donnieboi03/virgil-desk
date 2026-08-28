"""Hermes CLI invocation tests."""

import tempfile

import pytest

from desk_host.backends.hermes import HermesBackend, HermesRunResult, build_decompose_prompt


@pytest.mark.asyncio
async def test_hermes_run_uses_chat_query_flags(monkeypatch):
    captured: dict = {}

    def fake_run_sync(cmd, *, env, timeout):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["timeout"] = timeout
        return HermesRunResult(stdout='{"decomposition":"ok","items":[]}', stderr="", exit_code=0)

    async def fake_to_thread(func, *args, **kwargs):
        assert func is HermesBackend._hermes_run_sync
        return fake_run_sync(*args, **kwargs)

    monkeypatch.setattr("desk_host.backends.hermes.asyncio.to_thread", fake_to_thread)
    backend = HermesBackend()
    result = await backend._hermes_run("test prompt")
    assert isinstance(result, HermesRunResult)
    assert "-Q" in captured["cmd"]
    assert "-q" in captured["cmd"]
    assert "test prompt" in captured["cmd"]
    assert "--json" not in captured["cmd"]
    assert "--source" in captured["cmd"]


@pytest.mark.asyncio
async def test_hermes_run_passes_image_flag(monkeypatch):
    captured: dict = {}

    def fake_run_sync(cmd, *, env, timeout):
        captured["cmd"] = cmd
        return HermesRunResult(stdout="ok", stderr="", exit_code=0)

    async def fake_to_thread(func, *args, **kwargs):
        return fake_run_sync(*args, **kwargs)

    monkeypatch.setattr("desk_host.backends.hermes.asyncio.to_thread", fake_to_thread)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(b"\x89PNG\r\n")
        path = tmp.name
    backend = HermesBackend()
    await backend._hermes_run("vision prompt", image_path=path)
    assert "--image" in captured["cmd"]
    assert path in captured["cmd"]


def test_hermes_subprocess_env_sets_desk_bridge(monkeypatch):
    monkeypatch.delenv("DESK_HOST", raising=False)
    monkeypatch.delenv("DESK_PORT", raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    backend = HermesBackend()
    env = backend._hermes_subprocess_env(accept_hooks=True)
    assert env["HERMES_ACCEPT_HOOKS"] == "1"
    assert env["DESK_HOST"] == "127.0.0.1"
    assert env["DESK_PORT"] == "8787"
    assert "packages/host" in env["PYTHONPATH"]
    repo_root = backend._repo_root()
    assert str(repo_root / "scripts") in env["PATH"]


def test_hermes_subprocess_env_preserves_existing_desk_port(monkeypatch):
    monkeypatch.setenv("DESK_PORT", "9999")
    backend = HermesBackend()
    env = backend._hermes_subprocess_env(accept_hooks=False)
    assert env["DESK_PORT"] == "9999"


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
