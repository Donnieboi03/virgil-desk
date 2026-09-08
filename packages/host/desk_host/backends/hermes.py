"""Hermes agent backend — invokes configured Hermes profile."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..backends import new_run_id
from ..config import load_config
from ..decompose_parser import DecomposeError, parse_decompose_json
from ..observability import record, usage_measure
from ..execute_validation import (
    execute_summary_incomplete_reason,
    execute_summary_indicates_failure,
    strip_max_iter_banner,
)
from ..prompt_render import render_prompt
from ..screenshot_store import persist_handoff_screenshot

_SESSION_ID_LINE = re.compile(r"^session_id:\s*\S+\s*$", re.IGNORECASE | re.MULTILINE)
_API_FAILURE_HINTS = (
    "402",
    "404",
    "429",
    "timeout",
    "timed out",
    "rate limit",
    "insufficient",
    "budget",
    "payment required",
    "not found",
    "provider error",
    "api error",
)


def strip_session_id_noise(text: str) -> str:
    """Drop Hermes quiet-mode session_id footer lines."""
    if not text:
        return ""
    return _SESSION_ID_LINE.sub("", text).strip()


def format_hermes_summary(text: str, max_chars: int) -> str:
    cleaned = strip_max_iter_banner(strip_session_id_noise(text))
    if not cleaned:
        return ""
    return cleaned[:max_chars]


def format_hermes_failure(result: HermesRunResult) -> str:
    """Prefer stderr / API snippets over a bare session_id line."""
    stdout = strip_session_id_noise(result.stdout or "")
    stderr = strip_session_id_noise(result.stderr or "")
    combined = "\n".join(p for p in (stderr, stdout) if p).strip()
    lower = combined.lower()
    if any(h in lower for h in _API_FAILURE_HINTS):
        return combined
    if stderr and not stdout:
        return stderr
    if combined:
        return combined
    if result.exit_code:
        return f"hermes exit {result.exit_code}"
    return ""


def build_decompose_prompt(handoff: dict[str, Any]) -> str:
    cfg = load_config()
    system = render_prompt("decompose_handoff.md", cfg)
    snap = dict(handoff.get("snapshot") or {})
    snap.pop("screenshot", None)
    payload = {
        "url": handoff.get("url"),
        "title": handoff.get("title"),
        "intent": handoff.get("intent"),
        "agent_tab_id": handoff.get("agent_tab_id"),
        "snapshot": snap,
    }
    return f"{system}\n\n## Handoff\n\n```json\n{json.dumps(payload, indent=2)}\n```"


def build_execute_prompt(item: dict[str, Any], ctx: dict[str, Any]) -> str:
    system = render_prompt("execute_agent_item.md")
    payload = {"item": item, **ctx}
    return f"{system}\n\n## Task\n\n```json\n{json.dumps(payload, indent=2)}\n```"


@dataclass
class HermesRunResult:
    stdout: str
    stderr: str
    exit_code: int
    usage: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        return (self.stdout or self.stderr or "").strip()


_DESK_USAGE_LINE = re.compile(r"(?m)^DESK_USAGE:(\{.*\})\s*$")
_USAGE_WALK_KEYS = frozenset(
    {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
        "cost_usd",
        "usage",
    }
)


def _coerce_usage_dict(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize common token/cost keys into usage_measure-compatible shape."""
    mapped: dict[str, Any] = {}
    if "prompt_tokens" in raw:
        mapped["prompt_tokens"] = raw["prompt_tokens"]
    if "completion_tokens" in raw:
        mapped["completion_tokens"] = raw["completion_tokens"]
    if "total_tokens" in raw:
        mapped["total_tokens"] = raw["total_tokens"]
    cost = raw.get("cost_usd", raw.get("cost"))
    if cost is not None:
        mapped["cost_usd"] = cost
    cleaned = usage_measure(mapped)
    return cleaned or None


def _walk_usage(obj: Any, *, depth: int = 0) -> dict[str, Any] | None:
    if depth > 8:
        return None
    if isinstance(obj, dict):
        # Prefer nested usage object when present.
        nested = obj.get("usage")
        if isinstance(nested, dict):
            found = _coerce_usage_dict(nested)
            if found:
                return found
        found = _coerce_usage_dict(obj)
        if found:
            return found
        for key, val in obj.items():
            if key in _USAGE_WALK_KEYS or isinstance(val, (dict, list)):
                hit = _walk_usage(val, depth=depth + 1)
                if hit:
                    return hit
    elif isinstance(obj, list):
        for item in obj:
            hit = _walk_usage(item, depth=depth + 1)
            if hit:
                return hit
    return None


def extract_hermes_usage(
    *,
    home: str,
    stdout: str = "",
    stderr: str = "",
    started_at: float | None = None,
) -> dict[str, Any] | None:
    """Best-effort usage extract — never raises; returns None when unknown."""
    try:
        for blob in (stdout or "", stderr or ""):
            matches = list(_DESK_USAGE_LINE.finditer(blob))
            if not matches:
                continue
            try:
                raw = json.loads(matches[-1].group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                found = _coerce_usage_dict(raw)
                if found:
                    return found

        sessions_dir = Path(home).expanduser() / "sessions"
        if not sessions_dir.is_dir():
            return None
        candidates = sorted(
            sessions_dir.glob("session_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        import time as _time

        now = _time.time()
        window_start = (started_at or now) - 2.0
        for path in candidates[:12]:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < window_start or mtime > now + 5.0:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            found = _walk_usage(data)
            if found:
                return found
        return None
    except Exception:
        return None


class HermesBackend:
    def __init__(self) -> None:
        self.profile = os.environ.get("DESK_HERMES_PROFILE", "virgil-executor")
        self.home = os.path.expanduser(
            os.environ.get(
                "DESK_HERMES_HOME",
                f"~/.hermes/profiles/{self.profile}",
            )
        )

    async def decompose(self, handoff: dict[str, Any]) -> dict[str, Any]:
        run_id = handoff.get("run_id") or new_run_id()
        cfg = load_config()

        if cfg.hermes.decompose_enabled:
            prompt = build_decompose_prompt(handoff)
            image_path: str | None = None
            shot = (handoff.get("snapshot") or {}).get("screenshot")
            if shot and shot.get("base64"):
                image_path = persist_handoff_screenshot(run_id, shot)
            result = await self._hermes_run(
                prompt,
                image_path=image_path,
                skills=["desk-browser-bridge"],
                model=cfg.hermes.decompose_model,
                timeout_sec=cfg.hermes.decompose_timeout_sec,
            )
            parsed = parse_decompose_json(result.text, run_id, handoff)
            if parsed:
                parsed["live"] = True
                if result.usage:
                    parsed["usage"] = result.usage
                return parsed
            record(
                "handoff.decompose_failed",
                run_id,
                cfg=cfg,
                measure={
                    "exit_code": result.exit_code,
                    **(result.usage or {}),
                },
                reason="parse_failed" if result.text else "empty_output",
                stderr_snippet=(result.stderr or "")[: cfg.prompts.event_snippet_max_chars],
                stdout_snippet=(result.text or "")[: cfg.prompts.event_snippet_max_chars],
            )

        if cfg.hermes.decompose_fallback_stub:
            stub = self._stub_decompose(handoff, run_id)
            stub["live"] = False
            return stub

        raise DecomposeError("Hermes decompose failed and fallback disabled")

    async def execute_item(self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from ..app import dispatch_browser_command_and_wait

        cfg = load_config()
        run_id = ctx.get("run_id", "")
        human_tab = ctx.get("human_tab_id") or item.get("human_tab_id")
        agent_tab = ctx.get("agent_tab_id") or item.get("agent_tab_id")
        if human_tab is None or agent_tab is None:
            raise RuntimeError("execute missing human_tab_id or agent_tab_id")

        scrape = await dispatch_browser_command_and_wait(
            {
                "run_id": run_id,
                "op": "scrape",
                "human_tab_id": human_tab,
                "tab_id": agent_tab,
                "handoff_url": ctx.get("handoff_url", ""),
                "count_evidence": False,
            },
            timeout=cfg.host.browser_wait_timeout_sec,
        )
        if not scrape.get("ok", True):
            raise RuntimeError(scrape.get("error") or "initial scrape failed")

        excerpt_max = cfg.browser.scrape_excerpt_max_chars
        ctx = {
            **ctx,
            "initial_scrape": {
                "url": scrape.get("url"),
                "title": scrape.get("title"),
                "excerpt": (scrape.get("scrape_excerpt") or "")[:excerpt_max],
            },
        }
        prompt = build_execute_prompt(item, ctx)
        result = await self._hermes_run(
            prompt,
            skills=["desk-browser-bridge"],
            toolsets=cfg.hermes.execute_toolsets,
            accept_hooks=cfg.hermes.execute_accept_hooks,
            model=cfg.hermes.execute_model,
            max_turns=cfg.hermes.execute_max_turns,
            timeout_sec=cfg.hermes.execute_timeout_sec,
        )
        if result.exit_code != 0:
            raise RuntimeError(
                format_hermes_failure(result) or f"hermes exit {result.exit_code}"
            )
        if not result.text:
            raise RuntimeError("hermes execute returned empty output")
        summary = format_hermes_summary(result.text, cfg.prompts.execute_summary_max_chars)
        if not summary:
            raise RuntimeError(
                format_hermes_failure(result) or "hermes execute returned empty output"
            )
        if execute_summary_indicates_failure(summary):
            raise RuntimeError(summary)
        incomplete = execute_summary_incomplete_reason(summary)
        if incomplete:
            raise RuntimeError(
                incomplete
                if incomplete.lower().startswith("partial:")
                else f"Partial: {incomplete}"
            )
        out: dict[str, Any] = {"summary": summary, "exit_code": result.exit_code}
        if result.usage:
            out["usage"] = result.usage
        return out

    def _stub_decompose(self, handoff: dict[str, Any], run_id: str) -> dict[str, Any]:
        url = handoff.get("url", "")
        title = handoff.get("title") or url
        short = run_id.replace("desk_", "")[:8]
        agent_tab = handoff.get("agent_tab_id")
        human_tab = handoff.get("human_tab_id")
        return {
            "run_id": run_id,
            "decomposition": handoff.get("intent")
            or "Decompose this handoff into You/Agent/Waiting items.",
            "items": [
                {
                    "id": f"{run_id}_agent",
                    "column": "agent",
                    "title": f"Hermes: {title}",
                    "source": {"kind": "handoff", "url": url},
                    "status": "running",
                    "human_tab_id": human_tab,
                    "agent_tab_id": agent_tab,
                    "run_id": run_id,
                },
                {
                    "id": f"item_{short}_you",
                    "column": "you",
                    "title": "Review agent work and close",
                    "source": {"kind": "handoff", "url": url},
                    "status": "proposed",
                    "proposals": [],
                    "run_id": run_id,
                },
                {
                    "id": f"item_{short}_wait",
                    "column": "waiting",
                    "title": "Proposed calendar slot",
                    "source": {"kind": "handoff", "url": url},
                    "status": "proposed",
                    "run_id": run_id,
                    "proposals": [
                        {
                            "id": f"prop_{short}",
                            "kind": "calendar_slot",
                            "payload": {
                                "start": "2026-08-28T15:00:00-07:00",
                                "end": "2026-08-28T15:30:00-07:00",
                                "title": "Follow-up",
                            },
                            "requires": "accept",
                        }
                    ],
                },
            ],
        }

    async def desk_browser(self, command: dict[str, Any]) -> dict[str, Any]:
        from ..app import dispatch_browser_command_and_wait

        return await dispatch_browser_command_and_wait(command)

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[4]

    def _hermes_subprocess_env(self, *, accept_hooks: bool) -> dict[str, str]:
        """Env for Hermes CLI children — desk-browser must reach desk-host."""
        env = os.environ.copy()
        env["HERMES_HOME"] = self.home
        if accept_hooks:
            env["HERMES_ACCEPT_HOOKS"] = "1"
        env.setdefault("DESK_HOST", "127.0.0.1")
        env.setdefault("DESK_PORT", "8787")
        repo_root = self._repo_root()
        host_pkg = repo_root / "packages" / "host"
        pythonpath_parts = [str(host_pkg)]
        existing = env.get("PYTHONPATH", "")
        if existing:
            pythonpath_parts.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        repo_scripts = repo_root / "scripts"
        if repo_scripts.is_dir():
            env["PATH"] = f"{repo_scripts}{os.pathsep}{env.get('PATH', '')}"
        return env

    @staticmethod
    def _hermes_run_sync(
        cmd: list[str],
        *,
        env: dict[str, str],
        timeout: int,
    ) -> HermesRunResult:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
            return HermesRunResult(
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                exit_code=proc.returncode,
            )
        except FileNotFoundError:
            return HermesRunResult(stdout="", stderr="hermes CLI not found", exit_code=127)
        except subprocess.TimeoutExpired:
            return HermesRunResult(stdout="", stderr="hermes timeout", exit_code=124)

    async def _hermes_run(
        self,
        message: str,
        *,
        image_path: str | None = None,
        skills: list[str] | None = None,
        toolsets: list[str] | None = None,
        accept_hooks: bool = False,
        model: str | None = None,
        max_turns: int | None = None,
        timeout_sec: int | None = None,
    ) -> HermesRunResult:
        import time

        cfg = load_config()
        timeout = timeout_sec or cfg.hermes.decompose_timeout_sec
        env = self._hermes_subprocess_env(accept_hooks=accept_hooks)
        cmd = [
            "hermes",
            "-p",
            self.profile,
            "chat",
            "-Q",
            "-q",
            message,
            "--source",
            "tool",
        ]
        if model:
            cmd.extend(["-m", model])
        if max_turns is not None and max_turns > 0:
            cmd.extend(["--max-turns", str(max_turns)])
        if toolsets:
            cmd.extend(["-t", ",".join(toolsets)])
        if accept_hooks:
            cmd.append("--accept-hooks")
        if skills:
            for skill in skills:
                cmd.extend(["-s", skill])
        if image_path and Path(image_path).is_file():
            cmd.extend(["--image", image_path])
        started_at = time.time()
        result = await asyncio.to_thread(
            self._hermes_run_sync,
            cmd,
            env=env,
            timeout=timeout,
        )
        usage = extract_hermes_usage(
            home=self.home,
            stdout=result.stdout,
            stderr=result.stderr,
            started_at=started_at,
        )
        if usage:
            result.usage = usage
        return result

    async def execute_safe(self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        run_id = ctx.get("run_id", "")
        out = await self.execute_item(item, ctx)
        result = dict(item)
        result["status"] = "done"
        result["evidence"] = {"summary": out.get("summary", ""), **ctx}
        record(
            "run.finished",
            run_id,
            cfg=load_config(),
            backend="hermes",
            item_id=item.get("id"),
        )
        return result
