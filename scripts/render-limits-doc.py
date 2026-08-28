#!/usr/bin/env python3
"""Print LIMITS.md table rows from live config/desk.yaml (for doc refresh)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "host"))

from desk_host.config import config_schema_sections, load_config, repo_config_path  # noqa: E402

ENFORCED_BY: dict[str, str] = {
    "browser.scrape_text_max_chars": "Extension (from `/v1/config`)",
    "browser.scrape_links_max": "Extension",
    "browser.scrape_excerpt_max_chars": "Extension",
    "browser.handoff_excerpt_max_chars": "Extension",
    "browser.handoff_scroll_loops": "Extension (scroll agent tab before handoff scrape)",
    "browser.handoff_scroll_viewport_ratio": "Extension (fraction of viewport per scroll step)",
    "browser.screenshot_mode": "Extension",
    "browser.screenshot_max_per_run": "Host `policy.denied` / `screenshot_cap`",
    "browser.default_wait_ms": "Extension",
    "host.browser_wait_timeout_sec": "Host `/v1/browser` wait",
    "hermes.decompose_timeout_sec": "Hermes subprocess (decompose)",
    "hermes.execute_timeout_sec": "Hermes subprocess (Run agent execute)",
    "hermes.execute_require_browser_evidence": "Host rejects execute without `browser.command_result`",
    "hermes.decompose_fallback_stub": "Host Hermes backend",
    "hermes.decompose_enabled": "Host Hermes backend",
    "observability.persist_screenshots": "Host screenshot store",
    "prompts.decompose_items_max": "Hermes decompose prompt + parser truncates above cap",
    "prompts.decompose_summary_sentences_max": "Decompose JSON summary length hint",
    "prompts.work_item_title_max_chars": "Parser truncates item titles",
    "prompts.execute_summary_max_chars": "Execute result stored on WorkItem",
    "prompts.thin_scrape_threshold_chars": "Skill: when to add screenshot (guidance)",
    "prompts.agent_scroll_stall_loops": "Skill: scroll loops without progress (guidance)",
    "prompts.event_snippet_max_chars": "Observability log snippets",
    "prompts.event_summary_snippet_max_chars": "`agent.executed` summary in events",
}


def main() -> None:
    cfg = load_config()
    print(f"# Generated from `{repo_config_path()}` — run `python scripts/render-limits-doc.py`\n")
    print("| Key | Value | Enforced by |")
    print("|-----|-------|-------------|")
    for section, cls in config_schema_sections():
        block = getattr(cfg, section)
        for field in cls.__dataclass_fields__:  # type: ignore[attr-defined]
            key = f"{section}.{field}"
            val = getattr(block, field)
            enforced = ENFORCED_BY.get(key, "—")
            print(f"| `{key}` | {val!r} | {enforced} |")


if __name__ == "__main__":
    main()
