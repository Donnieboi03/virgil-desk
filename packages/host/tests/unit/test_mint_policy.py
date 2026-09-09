"""Mint idempotency helpers."""

from desk_host.mint_policy import find_idempotent_mint, normalize_resource_url


def test_normalize_resource_url():
    assert (
        normalize_resource_url(
            "https://My.SmartRecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc#frag"
        )
        == "https://my.smartrecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc"
    )
    assert normalize_resource_url(None) is None
    assert normalize_resource_url("https://ex.com/path/") == "https://ex.com/path"


def test_find_idempotent_mint_by_url():
    items = {
        "c1": {
            "id": "c1",
            "parent_id": "p1",
            "column": "you",
            "status": "proposed",
            "title": "Old title",
            "source": {
                "url": "https://my.smartrecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc"
            },
        }
    }
    hit = find_idempotent_mint(
        items,
        parent_id="p1",
        column="you",
        source_url="https://my.smartrecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc#x",
        title="New title",
    )
    assert hit and hit["id"] == "c1"
    assert (
        find_idempotent_mint(
            items,
            parent_id="p1",
            column="agent",
            source_url="https://my.smartrecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc",
        )
        is None
    )


def test_find_idempotent_mint_by_title_when_no_url():
    items = {
        "c1": {
            "id": "c1",
            "parent_id": "p1",
            "column": "you",
            "status": "proposed",
            "title": "Soft-help keywords",
            "source": {"kind": "handoff"},
        }
    }
    hit = find_idempotent_mint(
        items,
        parent_id="p1",
        column="you",
        source_url=None,
        title="Soft-help keywords",
    )
    assert hit and hit["id"] == "c1"
