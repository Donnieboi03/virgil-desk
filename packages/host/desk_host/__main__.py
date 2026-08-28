"""CLI entry: desk-host"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


def main() -> None:
    # Repo root .env (packages/host -> ../../.env) then cwd
    repo_env = Path(__file__).resolve().parents[3] / ".env"
    if repo_env.is_file():
        load_dotenv(repo_env)
    load_dotenv()

    host = os.environ.get("DESK_HOST", "127.0.0.1")
    port = int(os.environ.get("DESK_PORT", "8787"))
    uvicorn.run(
        "desk_host.app:app",
        host=host,
        port=port,
        reload=os.environ.get("DESK_RELOAD", "") == "1",
    )


if __name__ == "__main__":
    main()
