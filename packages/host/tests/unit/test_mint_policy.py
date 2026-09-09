"""Mint idempotency helpers."""

from desk_host.mint_policy import (
    find_idempotent_mint,
    normalize_gate_url,
    normalize_resource_url,
)


def test_normalize_resource_url():
    assert (
        normalize_resource_url(
            "https://My.SmartRecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc#frag"
        )
        == "https://my.smartrecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc"
    )
    assert normalize_resource_url(None) is None
    assert normalize_resource_url("https://ex.com/path/") == "https://ex.com/path"


def test_normalize_gate_url_drops_query():
    assert normalize_gate_url("https://Recruit.Net/apply?cf=1#frag") == "https://recruit.net/apply"
    assert normalize_gate_url("https://ex.com/path/?x=1") == "https://ex.com/path"


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


def test_gate_dedupe_collapses_query_variants():
    items = {
        "c1": {
            "id": "c1",
            "parent_id": "p1",
            "column": "you",
            "status": "proposed",
            "title": "Cloudflare",
            "park_kind": "auth_gate",
            "source": {"url": "https://jobs.example.com/apply?__cf_chl_tk=abc"},
        }
    }
    hit = find_idempotent_mint(
        items,
        parent_id="p1",
        column="you",
        source_url="https://jobs.example.com/apply?login=1",
        title="Login",
        gate_dedupe=True,
    )
    assert hit and hit["id"] == "c1"


def test_gate_dedupe_includes_done_auth_gate():
    items = {
        "c1": {
            "id": "c1",
            "parent_id": "p1",
            "column": "you",
            "status": "done",
            "title": "Cleared",
            "park_kind": "auth_gate",
            "resume": True,
            "source": {"url": "https://jobs.example.com/apply"},
        }
    }
    hit = find_idempotent_mint(
        items,
        parent_id="p1",
        column="you",
        source_url="https://jobs.example.com/apply?x=1",
        title="Again",
        gate_dedupe=True,
    )
    assert hit and hit["id"] == "c1"


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
