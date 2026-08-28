"""OpenClaw agent backend stub — same AgentBackend interface."""

from __future__ import annotations

from typing import Any

from .mock import MockBackend


class OpenClawBackend(MockBackend):
    """MVP: delegates to mock until OpenClaw API is configured."""

    async def decompose(self, handoff: dict[str, Any]) -> dict[str, Any]:
        out = await super().decompose(handoff)
        out["decomposition"] = f"[openclaw] {out['decomposition']}"
        return out
