# Limits

Canonical values live in [`config/desk.yaml`](../config/desk.yaml). Override via `DESK_CONFIG` path or env vars in [`ENV.md`](ENV.md).

| Key | Default | Enforced by |
|-----|---------|-------------|
| `browser.scrape_text_max_chars` | 16000 | Extension (from `/v1/config`) |
| `browser.scrape_links_max` | 200 | Extension |
| `browser.scrape_excerpt_max_chars` | 8000 | Extension |
| `browser.handoff_excerpt_max_chars` | 8000 | Extension |
| `browser.handoff_scroll_loops` | 2 | Extension (scroll agent tab before handoff scrape) |
| `browser.handoff_scroll_viewport_ratio` | 0.85 | Extension (fraction of viewport per scroll step) |
| `browser.screenshot_max_per_run` | 20 | Host `policy.denied` / `screenshot_cap` |
| `browser.default_wait_ms` | 500 | Extension |
| `host.browser_wait_timeout_sec` | 30 | Host `/v1/browser` wait |
| `hermes.decompose_timeout_sec` | 120 | Hermes subprocess (decompose) |
| `hermes.execute_timeout_sec` | 180 | Hermes subprocess (Run agent execute) |
| `hermes.execute_require_browser_evidence` | true | Host rejects execute without `browser.command_result` |

**Handoff snapshot screenshot** is captured client-side during **Hand off** (before any Host browser op). It does **not** count toward `screenshot_max_per_run`.

Skill-only guidance (not hard-enforced): thin scrape threshold 200 chars; ~4k vision tokens per screenshot.
