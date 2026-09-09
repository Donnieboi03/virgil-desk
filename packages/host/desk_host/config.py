"""Load config/desk.yaml (single source of truth) + env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


def repo_config_path() -> Path:
    env = os.environ.get("DESK_CONFIG", "").strip()
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[3] / "config" / "desk.yaml"


# Back-compat alias for internal imports
_repo_config_path = repo_config_path


@dataclass
class BrowserConfig:
    scrape_text_max_chars: int
    scrape_links_max: int
    scrape_excerpt_max_chars: int
    handoff_excerpt_max_chars: int
    handoff_scroll_loops: int
    handoff_scroll_viewport_ratio: float
    screenshot_mode: str
    screenshot_max_per_run: int
    default_wait_ms: int
    eyes_settle_budget_ms: int
    eyes_settle_poll_ms: int
    eyes_settle_min_text_chars: int
    eyes_deep_text_max_chars: int
    interact_targets_max: int
    observe_annotate_default: bool
    act_stall_max: int
    observe_followup_excerpt_max_chars: int
    observe_skip_screenshot_default: bool
    observe_all_frames: bool
    page_tree_max_chars: int
    page_tree_max_nodes: int
    driver: str
    harness_bin: str
    harness_bu_name: str


@dataclass
class HostConfig:
    browser_wait_timeout_sec: float


@dataclass
class HermesConfig:
    decompose_timeout_sec: int
    execute_timeout_sec: int
    execute_require_browser_evidence: bool
    decompose_fallback_stub: bool
    decompose_enabled: bool
    decompose_model: str
    execute_model: str
    execute_toolsets: list[str]
    execute_accept_hooks: bool
    execute_max_turns: int


@dataclass
class PromptsConfig:
    decompose_items_max: int
    decompose_summary_sentences_max: int
    work_item_title_max_chars: int
    execute_summary_max_chars: int
    event_snippet_max_chars: int
    event_summary_snippet_max_chars: int
    thin_scrape_threshold_chars: int
    agent_scroll_stall_loops: int


@dataclass
class ObservabilityConfig:
    persist_screenshots: bool


@dataclass
class MemoryConfig:
    recent_max: int
    notepad_max_bullets: int
    notepad_max_chars: int


@dataclass
class DeskConfig:
    browser: BrowserConfig
    host: HostConfig
    hermes: HermesConfig
    observability: ObservabilityConfig
    memory: MemoryConfig
    prompts: PromptsConfig


_CONFIG_SECTIONS: tuple[tuple[str, type], ...] = (
    ("browser", BrowserConfig),
    ("host", HostConfig),
    ("hermes", HermesConfig),
    ("observability", ObservabilityConfig),
    ("memory", MemoryConfig),
    ("prompts", PromptsConfig),
)


def _parse_section(cls: type, raw: Any, section: str) -> Any:
    if not isinstance(raw, dict):
        raise ValueError(f"desk.yaml: missing or invalid section '{section}'")
    names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    missing = names - set(raw)
    if missing:
        raise ValueError(
            f"desk.yaml [{section}] missing keys: {', '.join(sorted(missing))}"
        )
    unknown = set(raw) - names
    if unknown:
        raise ValueError(
            f"desk.yaml [{section}] unknown keys: {', '.join(sorted(unknown))}"
        )
    return cls(**{k: raw[k] for k in names})


def config_from_dict(data: dict[str, Any]) -> DeskConfig:
    return DeskConfig(
        browser=_parse_section(BrowserConfig, data.get("browser"), "browser"),
        host=_parse_section(HostConfig, data.get("host"), "host"),
        hermes=_parse_section(HermesConfig, data.get("hermes"), "hermes"),
        observability=_parse_section(
            ObservabilityConfig, data.get("observability"), "observability"
        ),
        memory=_parse_section(MemoryConfig, data.get("memory"), "memory"),
        prompts=_parse_section(PromptsConfig, data.get("prompts"), "prompts"),
    )


@lru_cache(maxsize=8)
def _read_yaml_document(path: str) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required to load desk.yaml")
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"desk config not found: {p}")
    with p.open(encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"desk.yaml must be a mapping: {p}")
    return loaded


def clear_config_cache() -> None:
    _read_yaml_document.cache_clear()


def load_config() -> DeskConfig:
    data = dict(_read_yaml_document(str(repo_config_path())))
    cfg = config_from_dict(data)

    if os.environ.get("DESK_SCREENSHOT_MAX_PER_RUN"):
        cfg.browser.screenshot_max_per_run = int(os.environ["DESK_SCREENSHOT_MAX_PER_RUN"])
    if os.environ.get("DESK_HERMES_DECOMPOSE") == "0":
        cfg.hermes.decompose_enabled = False
    if os.environ.get("DESK_PERSIST_SCREENSHOTS") == "1":
        cfg.observability.persist_screenshots = True
    if os.environ.get("DESK_BROWSER_DRIVER"):
        cfg.browser.driver = os.environ["DESK_BROWSER_DRIVER"].strip()
    if os.environ.get("BROWSER_HARNESS_BIN"):
        cfg.browser.harness_bin = os.environ["BROWSER_HARNESS_BIN"].strip()
    if os.environ.get("DESK_HARNESS_BU_NAME"):
        cfg.browser.harness_bu_name = os.environ["DESK_HARNESS_BU_NAME"].strip()

    return cfg


def config_for_extension(cfg: DeskConfig | None = None) -> dict[str, Any]:
    c = cfg or load_config()
    return {
        "browser": {
            "scrape_text_max_chars": c.browser.scrape_text_max_chars,
            "scrape_links_max": c.browser.scrape_links_max,
            "scrape_excerpt_max_chars": c.browser.scrape_excerpt_max_chars,
            "handoff_excerpt_max_chars": c.browser.handoff_excerpt_max_chars,
            "handoff_scroll_loops": c.browser.handoff_scroll_loops,
            "handoff_scroll_viewport_ratio": c.browser.handoff_scroll_viewport_ratio,
            "screenshot_mode": c.browser.screenshot_mode,
            "default_wait_ms": c.browser.default_wait_ms,
            "eyes_settle_budget_ms": c.browser.eyes_settle_budget_ms,
            "eyes_settle_poll_ms": c.browser.eyes_settle_poll_ms,
            "eyes_settle_min_text_chars": c.browser.eyes_settle_min_text_chars,
            "eyes_deep_text_max_chars": c.browser.eyes_deep_text_max_chars,
            "interact_targets_max": c.browser.interact_targets_max,
            "observe_annotate_default": c.browser.observe_annotate_default,
            "act_stall_max": c.browser.act_stall_max,
            "observe_followup_excerpt_max_chars": c.browser.observe_followup_excerpt_max_chars,
            "observe_skip_screenshot_default": c.browser.observe_skip_screenshot_default,
            "observe_all_frames": c.browser.observe_all_frames,
            "page_tree_max_chars": c.browser.page_tree_max_chars,
            "page_tree_max_nodes": c.browser.page_tree_max_nodes,
            "driver": c.browser.driver,
        },
        "host": {
            "browser_wait_timeout_sec": c.host.browser_wait_timeout_sec,
        },
        "memory": {
            "recent_max": c.memory.recent_max,
            "notepad_max_bullets": c.memory.notepad_max_bullets,
            "notepad_max_chars": c.memory.notepad_max_chars,
        },
    }


def config_schema_sections() -> tuple[tuple[str, type], ...]:
    """Section name + dataclass pairs (for tests and doc generation)."""
    return _CONFIG_SECTIONS
