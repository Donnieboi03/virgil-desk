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
