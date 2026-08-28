"""CLI entry: desk-host"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
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
