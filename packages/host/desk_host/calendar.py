"""Calendar accept handler — book only on explicit Accept."""

from __future__ import annotations

from typing import Any


def book_calendar_slot(payload: dict[str, Any]) -> dict[str, Any]:
    """Stub book path; Hermes/gws integration wires here in production."""
    return {
        "status": "booked_stub",
        "event_id": payload.get("event_id") or "stub_event",
        "start": payload.get("start"),
        "end": payload.get("end"),
        "title": payload.get("title") or "Virgil Desk meeting",
    }
