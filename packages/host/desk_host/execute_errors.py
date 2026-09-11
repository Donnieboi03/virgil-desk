"""Host-owned execute failure (backend-agnostic; mirrors HermesExecuteError shape for obs)."""

from __future__ import annotations

from typing import Any


class HostExecuteError(RuntimeError):
    """Host-loop execute failed — carries optional usage for observability."""

    def __init__(
        self,
        message: str,
        *,
        usage: dict[str, Any] | None = None,
        empty_output: bool = False,
        exit_code: int = 0,
    ) -> None:
        super().__init__(message)
        self.empty_output = bool(empty_output)
        self.usage = usage
        self.exit_code = int(exit_code)
        self.stdout = ""
        self.stderr = message
