# Limits

**Single source of truth:** [`config/desk.yaml`](../config/desk.yaml)

At runtime, `desk_host.config.load_config()` reads that file. Prompt `{{placeholders}}`, parser caps, extension `/v1/config`, and observability `limits` all use the loaded values — change the YAML and restart `desk-host` (reload extension for browser keys).

**Env overrides** (optional, see [`ENV.md`](ENV.md)): `DESK_CONFIG`, `DESK_SCREENSHOT_MAX_PER_RUN`, `DESK_HERMES_DECOMPOSE`, `DESK_PERSIST_SCREENSHOTS`.

**Schema:** each section in `desk.yaml` must match `desk_host.config` dataclass fields exactly (tests enforce key parity). Unknown or missing keys fail at load time.

Refresh a human-readable table after editing limits:

```bash
python scripts/render-limits-doc.py
```

**Handoff snapshot screenshot** is captured client-side during **Hand off** (before any Host browser op). It does **not** count toward `browser.screenshot_max_per_run`.

Prompt templates under `prompts/` use placeholders filled via `desk_host.prompt_render.render_prompt()`.
