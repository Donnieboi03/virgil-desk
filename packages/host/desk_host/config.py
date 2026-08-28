"""Load desk.yaml + env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


def _repo_config_path() -> Path:
    env = os.environ.get("DESK_CONFIG", "").strip()
    if env:
        return Path(env).expanduser()
    # packages/host/desk_host/config.py -> repo root
    return Path(__file__).resolve().parents[3] / "config" / "desk.yaml"


@dataclass
class BrowserConfig:
    scrape_text_max_chars: int = 16000
    scrape_links_max: int = 200
    scrape_excerpt_max_chars: int = 8000
    handoff_excerpt_max_chars: int = 8000
    handoff_scroll_loops: int = 2
    screenshot_mode: str = "captureVisibleTab"
    screenshot_max_per_run: int = 20
    default_wait_ms: int = 500


@dataclass
class HostConfig:
    browser_wait_timeout_sec: float = 30.0


@dataclass
class HermesConfig:
    decompose_timeout_sec: int = 120
    decompose_fallback_stub: bool = True
    decompose_enabled: bool = True


@dataclass
class ObservabilityConfig:
    persist_screenshots: bool = False


@dataclass
class DeskConfig:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    host: HostConfig = field(default_factory=HostConfig)
    hermes: HermesConfig = field(default_factory=HermesConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)


def _merge_section(cls: type, raw: dict[str, Any] | None) -> Any:
    if not raw:
        return cls()
    fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    return cls(**{k: v for k, v in raw.items() if k in fields})


def load_config() -> DeskConfig:
    path = _repo_config_path()
    data: dict[str, Any] = {}
    if yaml and path.is_file():
        with path.open(encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                data = loaded

    cfg = DeskConfig(
        browser=_merge_section(BrowserConfig, data.get("browser")),
        host=_merge_section(HostConfig, data.get("host")),
        hermes=_merge_section(HermesConfig, data.get("hermes")),
        observability=_merge_section(ObservabilityConfig, data.get("observability")),
    )

    if os.environ.get("DESK_SCREENSHOT_MAX_PER_RUN"):
        cfg.browser.screenshot_max_per_run = int(os.environ["DESK_SCREENSHOT_MAX_PER_RUN"])
    if os.environ.get("DESK_HERMES_DECOMPOSE") == "0":
        cfg.hermes.decompose_enabled = False
    if os.environ.get("DESK_PERSIST_SCREENSHOTS") == "1":
        cfg.observability.persist_screenshots = True

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
            "screenshot_mode": c.browser.screenshot_mode,
            "default_wait_ms": c.browser.default_wait_ms,
        },
        "host": {
            "browser_wait_timeout_sec": c.host.browser_wait_timeout_sec,
        },
    }
