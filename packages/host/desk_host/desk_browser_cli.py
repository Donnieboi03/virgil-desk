"""CLI wrapper for Host POST /v1/browser — Hermes terminal invokes this."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from desk_host.thin_browser_result import thin_browser_response


def _post_json(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    parser.add_argument(
        "--skip-screenshot",
        action="store_true",
        help="Skip viewport capture (default for Path B observe via host config)",
    )
    args = parser.parse_args()

    host = os.environ.get("DESK_HOST", "127.0.0.1")
    port = os.environ.get("DESK_PORT", "8787")
    base = f"http://{host}:{port}"

    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError:
        print("Invalid --params JSON", file=sys.stderr)
        return 2

    # Mid-flight board mint (not a browser op).
    if args.op == "mint_item":
        parent_id = params.get("parent_id")
        title = params.get("title")
        column = params.get("column")
        if not parent_id or not title or not column:
            print(
                "mint_item requires --params with parent_id, column, title",
                file=sys.stderr,
            )
            return 2
        body = {
            "run_id": args.run_id,
            "parent_id": parent_id,
            "column": column,
            "title": title,
            "status": params.get("status") or "proposed",
        }
        if params.get("hints"):
            body["hints"] = params["hints"]
        if params.get("source"):
            body["source"] = params["source"]
        elif args.url:
            body["source"] = {"kind": "handoff", "url": args.url}
        try:
            out = _post_json(f"{base}/v1/items/mint", body, args.timeout + 5)
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            print(err or exc.reason, file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            print(str(exc.reason), file=sys.stderr)
            return 1
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok", True) else 1

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
    if args.skip_screenshot:
        body["skip_screenshot"] = True

    try:
        out = _post_json(f"{base}/v1/browser", body, args.timeout + 5)
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
