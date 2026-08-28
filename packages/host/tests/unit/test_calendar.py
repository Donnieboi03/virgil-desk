from desk_host.calendar import book_calendar_slot


def test_book_calendar_slot_stub():
    out = book_calendar_slot({"start": "2026-08-28T15:00:00", "title": "Sync"})
    assert out["status"] == "booked_stub"
    assert out["title"] == "Sync"
