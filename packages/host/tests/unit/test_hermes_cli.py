"""Hermes CLI invocation tests."""

import tempfile

import pytest

from desk_host.backends.hermes import (
    HermesBackend,
    HermesRunResult,
    build_decompose_prompt,
    format_hermes_failure,
    format_hermes_summary,
    strip_session_id_noise,
)
from desk_host.config import load_config


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
async def test_hermes_run_passes_model_flag(monkeypatch):
    captured: dict = {}

    def fake_run_sync(cmd, *, env, timeout):
        captured["cmd"] = cmd
        return HermesRunResult(stdout="ok", stderr="", exit_code=0)

    async def fake_to_thread(func, *args, **kwargs):
        return fake_run_sync(*args, **kwargs)

    monkeypatch.setattr("desk_host.backends.hermes.asyncio.to_thread", fake_to_thread)
    backend = HermesBackend()
    await backend._hermes_run("p", model="google/gemini-3.7-flash")
    assert "-m" in captured["cmd"]
    assert "google/gemini-3.7-flash" in captured["cmd"]


@pytest.mark.asyncio
async def test_hermes_run_passes_max_turns_flag(monkeypatch):
    captured: dict = {}

    def fake_run_sync(cmd, *, env, timeout):
        captured["cmd"] = cmd
        return HermesRunResult(stdout="ok", stderr="", exit_code=0)

    async def fake_to_thread(func, *args, **kwargs):
        return fake_run_sync(*args, **kwargs)

    monkeypatch.setattr("desk_host.backends.hermes.asyncio.to_thread", fake_to_thread)
    backend = HermesBackend()
    await backend._hermes_run("p", max_turns=12)
    assert "--max-turns" in captured["cmd"]
    assert "12" in captured["cmd"]


@pytest.mark.asyncio
async def test_decompose_uses_decompose_model(monkeypatch):
    captured: dict = {}
    cfg = load_config()

    async def fake_run(self, message, **kwargs):
        captured["model"] = kwargs.get("model")
        captured["accept_hooks"] = kwargs.get("accept_hooks", False)
        captured["max_turns"] = kwargs.get("max_turns")
        return HermesRunResult(
            stdout='{"decomposition":"ok","items":[]}',
            stderr="",
            exit_code=0,
        )

    monkeypatch.setattr(HermesBackend, "_hermes_run", fake_run)
    backend = HermesBackend()
    await backend.decompose(
        {
            "run_id": "desk_model_test",
            "url": "https://example.com",
            "title": "T",
            "snapshot": {"excerpt": "hi"},
        }
    )
    assert captured["model"] == cfg.hermes.decompose_model
    assert captured["accept_hooks"] is False
    assert captured["max_turns"] is None


@pytest.mark.asyncio
async def test_execute_uses_execute_model_and_hooks_off(monkeypatch):
    captured: dict = {}
    cfg = load_config()

    async def fake_scrape(*_a, **_k):
        return {
            "ok": True,
            "url": "https://example.com",
            "title": "T",
            "scrape_excerpt": "body",
        }

    async def fake_run(self, message, **kwargs):
        captured["model"] = kwargs.get("model")
        captured["accept_hooks"] = kwargs.get("accept_hooks")
        captured["max_turns"] = kwargs.get("max_turns")
        return HermesRunResult(stdout="Done looking.", stderr="", exit_code=0)

    monkeypatch.setattr(
        "desk_host.app.dispatch_browser_command_and_wait",
        fake_scrape,
    )
    monkeypatch.setattr(HermesBackend, "_hermes_run", fake_run)
    monkeypatch.setenv("DESK_AGENT_BACKEND", "hermes")
    backend = HermesBackend()
    out = await backend.execute_item(
        {"id": "i1", "title": "t", "column": "agent"},
        {
            "run_id": "desk_exec_model",
            "human_tab_id": 1,
            "agent_tab_id": 2,
            "handoff_url": "https://example.com",
        },
    )
    assert out["summary"]
    assert captured["model"] == cfg.hermes.execute_model
    assert captured["accept_hooks"] is False
    assert cfg.hermes.execute_accept_hooks is False
    assert captured["max_turns"] == cfg.hermes.execute_max_turns
    assert cfg.hermes.execute_max_turns == 20


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


def test_strip_session_id_noise():
    assert strip_session_id_noise("hello\nsession_id: 20260828_abc\n") == "hello"
    assert strip_session_id_noise("session_id: only") == ""


def test_format_hermes_failure_strips_session_id_on_stderr():
    result = HermesRunResult(
        stdout="",
        stderr="session_id: 20260907_desk_ebd0327b51ab48f6",
        exit_code=1,
    )
    assert format_hermes_failure(result) == "hermes exit 1"
    assert (
        format_hermes_failure(
            HermesRunResult(
                stdout="session_id: abc",
                stderr="session_id: abc",
                exit_code=1,
            )
        )
        == "hermes exit 1"
    )


def test_format_hermes_failure_prefers_api_stderr():
    result = HermesRunResult(
        stdout="session_id: 20260828_151357_92bd36",
        stderr="Error: OpenRouter 402 insufficient credits / budget",
        exit_code=1,
    )
    msg = format_hermes_failure(result)
    assert "402" in msg
    assert "session_id" not in msg.lower() or "402" in msg


def test_format_hermes_summary_drops_session_only():
    assert format_hermes_summary("session_id: abc\n", 200) == ""
    assert format_hermes_summary("Done.\nsession_id: abc\n", 200) == "Done."
