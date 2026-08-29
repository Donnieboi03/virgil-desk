"""CLI wrapper for Host POST /v1/browser — Hermes terminal invokes this."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from desk_host.thin_browser_result import thin_browser_response


def main() -> int:
    parser = argparse.ArgumentParser(description="Virgil Desk browser bridge CLI")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--op", required=True)
    parser.add_argument("--human-tab-id", type=int)
    parser.add_argument("--tab-id", type=int)
    parser.add_argument("--url")
    parser.add_argument("--handoff-url")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    host = os.environ.get("DESK_HOST", "127.0.0.1")
    port = os.environ.get("DESK_PORT", "8787")
    base = f"http://{host}:{port}"

    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError:
        print("Invalid --params JSON", file=sys.stderr)
        return 2

    body: dict = {
        "run_id": args.run_id,
        "op": args.op,
        "wait": args.wait,
        "wait_timeout_sec": args.timeout,
    }
    if args.human_tab_id is not None:
        body["human_tab_id"] = args.human_tab_id
    if args.tab_id is not None:
        body["tab_id"] = args.tab_id
    if args.url:
        body["url"] = args.url
    if args.handoff_url:
        body["handoff_url"] = args.handoff_url
    if params:
        body["params"] = params

    req = urllib.request.Request(
        f"{base}/v1/browser",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout + 5) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        print(err or exc.reason, file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(str(exc.reason), file=sys.stderr)
        return 1

    print(json.dumps(thin_browser_response(out), indent=2))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
