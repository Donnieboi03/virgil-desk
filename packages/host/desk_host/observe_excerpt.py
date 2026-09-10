"""Pure observe/act excerpt thinning (mirrors extension observeExcerpt.js)."""

from __future__ import annotations

from typing import Any


OMIT_NOTE = (
    "text_omitted: url unchanged since last full excerpt — "
    "use interact_targets; re-observe after navigation"
)


def decide_excerpt(
    *,
    url: str,
    text: str,
    last_full_text_url: str | None,
    full_max: int,
    followup_max: int,
) -> dict[str, Any]:
    page_url = url or ""
    raw = text or ""
    if last_full_text_url and page_url and page_url == last_full_text_url:
        return {
            "text": "",
            "text_omitted": True,
            "note": OMIT_NOTE,
            "next_baseline": last_full_text_url,
        }
    cap = (
        followup_max
        if last_full_text_url and page_url and page_url != last_full_text_url
        else full_max
    )
    max_chars = max(0, int(cap or 0))
    return {
        "text": raw[:max_chars],
        "text_omitted": False,
        "note": None,
        "next_baseline": page_url or last_full_text_url or "",
    }
