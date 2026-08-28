"""Hermes agent backend — invokes configured Hermes profile."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..backends import new_run_id
from ..config import load_config
from ..decompose_parser import DecomposeError, parse_decompose_json
from ..observability import record
from ..prompt_render import render_prompt
from ..screenshot_store import persist_handoff_screenshot


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

    @property
    def text(self) -> str:
        return (self.stdout or self.stderr or "").strip()


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
                timeout_sec=cfg.hermes.decompose_timeout_sec,
            )
            parsed = parse_decompose_json(result.text, run_id, handoff)
            if parsed:
                parsed["live"] = True
                return parsed
            record(
                "handoff.decompose_failed",
                run_id,
                cfg=cfg,
                measure={"exit_code": result.exit_code},
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
        prompt = build_execute_prompt(item, ctx)
        cfg = load_config()
        result = await self._hermes_run(
            prompt,
            skills=["desk-browser-bridge"],
            timeout_sec=cfg.hermes.execute_timeout_sec,
        )
        if result.exit_code != 0:
            raise RuntimeError(
                result.stderr or result.text or f"hermes exit {result.exit_code}"
            )
        if not result.text:
            raise RuntimeError("hermes execute returned empty output")
        max_chars = cfg.prompts.execute_summary_max_chars
        return {"summary": result.text[:max_chars], "exit_code": result.exit_code}

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

    async def _hermes_run(
        self,
        message: str,
        *,
        image_path: str | None = None,
        skills: list[str] | None = None,
        timeout_sec: int | None = None,
    ) -> HermesRunResult:
        cfg = load_config()
        timeout = timeout_sec or cfg.hermes.decompose_timeout_sec
        env = os.environ.copy()
        env["HERMES_HOME"] = self.home
        repo_scripts = Path(__file__).resolve().parents[4] / "scripts"
        if repo_scripts.is_dir():
            env["PATH"] = f"{repo_scripts}{os.pathsep}{env.get('PATH', '')}"
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
        if skills:
            for skill in skills:
                cmd.extend(["-s", skill])
        if image_path and Path(image_path).is_file():
            cmd.extend(["--image", image_path])
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
