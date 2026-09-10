"""Unit tests for observe excerpt omit/cap decision."""

from desk_host.observe_excerpt import decide_excerpt


def test_first_visit_full():
    r = decide_excerpt(
        url="https://mail/inbox",
        text="x" * 500,
        last_full_text_url=None,
        full_max=100,
        followup_max=40,
    )
    assert r["text_omitted"] is False
    assert len(r["text"]) == 100
    assert r["next_baseline"] == "https://mail/inbox"


def test_same_url_omits():
    url = "https://mail/inbox"
    r = decide_excerpt(
        url=url,
        text="inbox",
        last_full_text_url=url,
        full_max=1000,
        followup_max=40,
    )
    assert r["text_omitted"] is True
    assert r["text"] == ""
    assert "text_omitted" in (r["note"] or "")


def test_url_change_caps_followup():
    r = decide_excerpt(
        url="https://mail/thread/1",
        text="y" * 200,
        last_full_text_url="https://mail/inbox",
        full_max=1000,
        followup_max=40,
    )
    assert r["text_omitted"] is False
    assert len(r["text"]) == 40
    assert r["next_baseline"] == "https://mail/thread/1"
