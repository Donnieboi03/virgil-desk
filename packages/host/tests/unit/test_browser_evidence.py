"""Browser evidence counting for execute gate."""

import threading

from starlette.testclient import TestClient

from desk_host.app import _browser_results_for_run, app, reset_state_for_tests
from helpers.mock_extension import MockExtensionSession, run_browser_wait


def test_count_evidence_false_skips_browser_result_count():
    run_id = "desk_evidence_flag"
    with TestClient(app) as client:
        ext = MockExtensionSession(client)
        try:
            pending = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "scrape",
                    "human_tab_id": 1,
                    "tab_id": 2,
                    "count_evidence": False,
                    "wait": True,
                },
            )
            ext.respond_next_browser_command(run_id=run_id, op="scrape")
            pending["thread"].join(timeout=5)
            assert pending["holder"][0]["status"] == 200
            assert _browser_results_for_run(run_id) == 0

            pending2 = run_browser_wait(
                client,
                {
                    "run_id": run_id,
                    "op": "observe",
                    "human_tab_id": 1,
                    "tab_id": 2,
                    "wait": True,
                },
            )
            ext.respond_next_browser_command(run_id=run_id, op="observe")
            pending2["thread"].join(timeout=5)
            assert pending2["holder"][0]["status"] == 200
            assert _browser_results_for_run(run_id) == 1
        finally:
            ext.close()
            reset_state_for_tests()
