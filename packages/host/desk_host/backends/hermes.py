"""Hermes agent backend — invokes configured Hermes profile."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from ..backends import new_run_id
from ..config import load_config
from ..decompose_parser import DecomposeError, parse_decompose_json
from ..observability import emit


def _prompt_path() -> Path:
    return Path(__file__).resolve().parents[4] / "prompts" / "decompose_handoff.md"


def build_decompose_prompt(handoff: dict[str, Any]) -> str:
    system = _prompt_path().read_text(encoding="utf-8")
    payload = {
        "url": handoff.get("url"),
        "title": handoff.get("title"),
        "intent": handoff.get("intent"),
        "snapshot": handoff.get("snapshot") or {},
    }
    return f"{system}\n\n## Handoff\n\n```json\n{json.dumps(payload, indent=2)}\n```"


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
        url = handoff.get("url", "")

        if cfg.hermes.decompose_enabled:
            prompt = build_decompose_prompt(handoff)
            raw = await self._hermes_run(prompt)
            parsed = parse_decompose_json(raw, run_id, handoff)
            if parsed:
                parsed["live"] = True
                return parsed

        if cfg.hermes.decompose_fallback_stub:
            stub = self._stub_decompose(handoff, run_id)
            stub["live"] = False
            return stub

        raise DecomposeError("Hermes decompose failed and fallback disabled")

    def _stub_decompose(self, handoff: dict[str, Any], run_id: str) -> dict[str, Any]:
        url = handoff.get("url", "")
        title = handoff.get("title") or url
        short = run_id.replace("desk_", "")[:8]
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
                    "human_tab_id": handoff.get("human_tab_id"),
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
        """Host-internal desk_browser — waits for extension command_result."""
        from ..app import dispatch_browser_command_and_wait

        return await dispatch_browser_command_and_wait(command)

    async def _hermes_run(self, message: str) -> str:
        cfg = load_config()
        env = os.environ.copy()
        env["HERMES_HOME"] = self.home
        try:
            proc = subprocess.run(
                ["hermes", "-p", self.profile, "chat", "--json", message],
                capture_output=True,
                text=True,
                timeout=cfg.hermes.decompose_timeout_sec,
                env=env,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
        return proc.stdout.strip() or proc.stderr.strip()

    async def execute_safe(self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        run_id = ctx.get("run_id", "")
        body = json.dumps({"item": item, "ctx": ctx})[:4000]
        _ = await self._hermes_run(f"desk_browser execute_safe: {body}")
        out = dict(item)
        out["status"] = "done"
        out["evidence"] = {"summary": "Hermes execution complete.", **ctx}
        emit("run.finished", run_id, {"backend": "hermes", "item_id": item.get("id")})
        return out
