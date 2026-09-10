"""Agent backend adapters."""

from __future__ import annotations

import os
import uuid
from typing import Any, Protocol


class AgentBackend(Protocol):
    async def decompose(self, handoff: dict[str, Any]) -> dict[str, Any]: ...

    async def execute_item(self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]: ...

    async def execute_safe(self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]: ...


def new_run_id() -> str:
    return f"desk_{uuid.uuid4().hex[:16]}"


def get_backend() -> AgentBackend:
    name = os.environ.get("DESK_AGENT_BACKEND", "mock").strip().lower()
    if name == "hermes":
        from .hermes import HermesBackend

        return HermesBackend()
    if name == "openclaw":
        from .openclaw import OpenClawBackend

        return OpenClawBackend()
    from .mock import MockBackend

    return MockBackend()
