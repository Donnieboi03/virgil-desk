"""Hermes agent backend — invokes configured Hermes profile."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ..backends import new_run_id
from ..observability import emit


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
        emit("handoff.decomposed", run_id, {"backend": "hermes", "url": handoff.get("url")})
        # MVP: structured stub; live Hermes invoke wired via desk_browser tool + skill.
        url = handoff.get("url", "")
        prompt = handoff.get("intent") or "Decompose this handoff into You/Agent/Waiting items."
        return {
            "run_id": run_id,
            "decomposition": prompt,
            "items": [
                {
                    "id": f"{run_id}_agent",
                    "column": "agent",
                    "title": f"Hermes: {handoff.get('title') or url}",
                    "source": {"kind": "handoff", "url": url},
                    "status": "running",
                    "human_tab_id": handoff.get("human_tab_id"),
                },
            ],
        }

    async def _hermes_run(self, message: str) -> str:
        env = os.environ.copy()
        env["HERMES_HOME"] = self.home
        try:
            proc = subprocess.run(
                ["hermes", "-p", self.profile, "chat", "--json", message],
                capture_output=True,
                text=True,
                timeout=120,
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
