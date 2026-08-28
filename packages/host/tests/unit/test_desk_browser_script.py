"""desk-browser CLI POST body tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "desk-browser"


def test_desk_browser_builds_scrape_post():
    ns: dict = {}
    exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), ns)

    with patch("urllib.request.urlopen") as urlopen:
        resp = MagicMock()
        resp.read.return_value = json.dumps({"ok": True}).encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        urlopen.return_value = resp

        old_argv = sys.argv
        sys.argv = [
            "desk-browser",
            "--run-id",
            "desk_test123",
            "--op",
            "scrape",
            "--human-tab-id",
            "10",
            "--tab-id",
            "20",
            "--wait",
        ]
        try:
            assert ns["main"]() == 0
        finally:
            sys.argv = old_argv

        req = urlopen.call_args[0][0]
        assert req.full_url.endswith("/v1/browser")
        body = json.loads(req.data.decode())
        assert body["run_id"] == "desk_test123"
        assert body["op"] == "scrape"
        assert body["human_tab_id"] == 10
        assert body["tab_id"] == 20
        assert body["wait"] is True
