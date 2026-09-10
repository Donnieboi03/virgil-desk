"""Mock agent backend for E2E and CI."""

from __future__ import annotations

from typing import Any

from ..backends import new_run_id


class MockBackend:
    async def decompose(self, handoff: dict[str, Any]) -> dict[str, Any]:
        run_id = handoff.get("run_id") or new_run_id()
        url = handoff.get("url", "")
        return {
            "run_id": run_id,
            "decomposition": "Agent can research this page; you decide whether to apply.",
            "items": [
                {
                    "id": f"item_{run_id[:8]}_agent",
                    "column": "agent",
                    "title": f"Research: {handoff.get('title') or url}",
                    "source": {"kind": "handoff", "url": url},
                    "status": "running",
                    "human_tab_id": handoff.get("human_tab_id"),
                    "agent_tab_id": handoff.get("agent_tab_id"),
                    "run_id": run_id,
                },
                {
                    "id": f"item_{run_id[:8]}_you",
                    "column": "you",
                    "title": "Review and close when ready",
                    "source": {"kind": "handoff", "url": url},
                    "status": "proposed",
                    "proposals": [],
                    "run_id": run_id,
                },
                {
                    "id": f"item_{run_id[:8]}_wait",
                    "column": "waiting",
                    "title": "Proposed calendar slot",
                    "source": {"kind": "handoff", "url": url},
                    "status": "proposed",
                    "run_id": run_id,
                    "proposals": [
                        {
                            "id": f"prop_{run_id[:8]}",
                            "kind": "calendar_slot",
                            "payload": {
                                "start": "2026-08-28T15:00:00-07:00",
                                "end": "2026-08-28T15:30:00-07:00",
                                "title": "Follow-up",
                            },
                            "requires": "accept",
                        }
                    ],
                },
            ],
        }

    async def execute_item(self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        from ..app import dispatch_browser_command_and_wait

        run_id = ctx.get("run_id", "")
        await dispatch_browser_command_and_wait(
            {
                "run_id": run_id,
                "op": "scrape",
                "human_tab_id": ctx.get("human_tab_id") or item.get("human_tab_id"),
                "tab_id": ctx.get("agent_tab_id") or item.get("agent_tab_id"),
                "count_evidence": False,
            }
        )
        result = await dispatch_browser_command_and_wait(
            {
                "run_id": run_id,
                "op": "observe",
                "human_tab_id": ctx.get("human_tab_id") or item.get("human_tab_id"),
                "tab_id": ctx.get("agent_tab_id") or item.get("agent_tab_id"),
            }
        )
        excerpt = (result.get("scrape_excerpt") or "")[:500]
        return {"summary": f"Mock agent finished: {excerpt or 'observe ok'}"}

    async def execute_safe(self, item: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        out = dict(item)
        out["status"] = "done"
        out["evidence"] = {
            "summary": "Mock agent finished research.",
            "scrape_excerpt": ctx.get("scrape_excerpt", ""),
        }
        return out
