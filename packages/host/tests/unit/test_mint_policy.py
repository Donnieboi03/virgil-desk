"""URL normalize helpers."""

from desk_host.mint_policy import normalize_resource_url


def test_normalize_resource_url():
    assert (
        normalize_resource_url(
            "https://My.SmartRecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc#frag"
        )
        == "https://my.smartrecruiters.com/oneclick-ui/screening/task/expired-or-not-found?dcr_cmi=abc"
    )
    assert normalize_resource_url(None) is None
    assert normalize_resource_url("https://ex.com/path/") == "https://ex.com/path"
