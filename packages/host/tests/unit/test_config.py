from desk_host.config import BrowserConfig, load_config


def test_load_config_defaults():
    cfg = load_config()
    assert cfg.browser.scrape_text_max_chars == 16000
    assert cfg.browser.handoff_excerpt_max_chars == 8000
    assert cfg.browser.handoff_scroll_loops == 2
    assert cfg.browser.screenshot_max_per_run == 20


def test_browser_config_fields():
    b = BrowserConfig()
    assert b.screenshot_mode == "captureVisibleTab"
