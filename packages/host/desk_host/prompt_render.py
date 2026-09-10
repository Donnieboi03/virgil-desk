"""Inject config/desk.yaml prompt limits into markdown templates."""

from __future__ import annotations

from pathlib import Path

from .config import DeskConfig, PromptsConfig, load_config


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "prompts"


def prompt_template_vars(cfg: DeskConfig | None = None) -> dict[str, str]:
    c = cfg or load_config()
    p = c.prompts
    b = c.browser
    return {
        "decompose_items_max": str(p.decompose_items_max),
        "decompose_summary_sentences_max": str(p.decompose_summary_sentences_max),
        "work_item_title_max_chars": str(p.work_item_title_max_chars),
        "handoff_excerpt_max_chars": str(b.handoff_excerpt_max_chars),
        "handoff_scroll_loops": str(b.handoff_scroll_loops),
        "thin_scrape_threshold_chars": str(p.thin_scrape_threshold_chars),
        "agent_scroll_stall_loops": str(p.agent_scroll_stall_loops),
        "screenshot_max_per_run": str(b.screenshot_max_per_run),
    }


def render_prompt(name: str, cfg: DeskConfig | None = None) -> str:
    text = (_prompts_dir() / name).read_text(encoding="utf-8")
    for key, value in prompt_template_vars(cfg).items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text
