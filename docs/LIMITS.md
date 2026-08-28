# Limits

Canonical values live in [`config/desk.yaml`](../config/desk.yaml). Override via `DESK_CONFIG` path or env vars in [`ENV.md`](ENV.md).

| Key | Default | Enforced by |
|-----|---------|-------------|
| `browser.scrape_text_max_chars` | 8000 | Extension (from `/v1/config`) |
| `browser.scrape_links_max` | 50 | Extension |
| `browser.scrape_excerpt_max_chars` | 4000 | Extension |
| `browser.handoff_excerpt_max_chars` | 2000 | Extension |
| `browser.screenshot_max_per_run` | 20 | Host `policy.denied` / `screenshot_cap` |
| `browser.default_wait_ms` | 500 | Extension |
| `host.browser_wait_timeout_sec` | 30 | Host `/v1/browser` wait |
| `hermes.decompose_timeout_sec` | 120 | Hermes subprocess |

Skill-only guidance (not hard-enforced): thin scrape threshold 200 chars; ~4k vision tokens per screenshot.
