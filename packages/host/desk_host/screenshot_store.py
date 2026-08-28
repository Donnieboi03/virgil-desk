"""Optional PNG persist under ~/.virgil-desk/runs/."""

from __future__ import annotations

import base64
import re
from pathlib import Path


def runs_dir(run_id: str) -> Path:
    root = Path.home() / ".virgil-desk" / "runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def persist_screenshot(run_id: str, command_id: str, screenshot: dict) -> str | None:
    b64 = screenshot.get("base64")
    if not b64:
        return None
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", command_id)[:64]
    path = runs_dir(run_id) / f"{safe}.png"
    path.write_bytes(base64.b64decode(b64))
    return str(path)
