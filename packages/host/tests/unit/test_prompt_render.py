"""Unit tests for prompt template rendering."""

import re

from desk_host.config import load_config
from desk_host.prompt_render import prompt_template_vars, render_prompt


def test_decompose_prompt_injects_live_config():
    cfg = load_config()
    text = render_prompt("decompose_handoff.md", cfg)
    max_items = cfg.prompts.decompose_items_max
    excerpt_max = cfg.browser.handoff_excerpt_max_chars
    scroll_loops = cfg.browser.handoff_scroll_loops

    assert "{{" not in text, "unresolved prompt placeholders"
    assert str(max_items) in text
    assert f"Up to **{max_items} items**" in text
    assert str(excerpt_max) in text
    assert str(scroll_loops) in text


def test_prompt_template_vars_match_config():
    cfg = load_config()
    vars_ = prompt_template_vars(cfg)
    assert vars_["decompose_items_max"] == str(cfg.prompts.decompose_items_max)
    assert vars_["handoff_excerpt_max_chars"] == str(cfg.browser.handoff_excerpt_max_chars)
    assert not any(re.search(r"\{\{", v) for v in vars_.values())


def test_execute_prompt_dom_primary_playbooks():
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    text = (root / "prompts" / "execute_agent_item.md").read_text(encoding="utf-8")
    assert "DOM Eyes" in text
    assert "secondary workaround" in text
    assert "Auth wall" in text or "auth wall" in text.lower() or "auth_gate" in text
    assert "social send" in text.lower() or "outbound social" in text.lower() or "connect" in text.lower()
    assert "email **drafts**" in text or "email drafts" in text.lower()
    assert "last resort" in text.lower()
    assert "agent-continue" in text.lower() or "Agent-continue" in text or "agent tab" in text
    assert "eyes_empty" in text or "invent page copy" in text.lower()
    assert "eyes_mode" in text
    assert "eyes_hints" in text
    assert "Verified terminal" in text or "verified terminal" in text.lower()
    assert "Completed" in text or "no further action" in text.lower()
    assert "awaiting_human" in text or "auth_gate" in text
    assert "park_kind" in text
    assert "human_park_tab_denied" in text
    assert "placement:human" in text or "placement=human" in text
