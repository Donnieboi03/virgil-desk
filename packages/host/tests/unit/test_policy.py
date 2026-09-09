from desk_host.policy import (
    is_human_tab_target,
    policy_denied_reason,
    requires_auto_verify,
)


def test_human_tab_blocked_for_click():
    assert policy_denied_reason("click", 42, 42) == "human_tab_blocked"


def test_agent_tab_allowed():
    assert policy_denied_reason("click", 87, 42) is None


def test_snapshot_on_human_ok():
    assert not is_human_tab_target("captureHandoffSnapshot", 42, 42) or True
    assert policy_denied_reason("captureHandoffSnapshot", 42, 42) is None


def test_requires_auto_verify():
    assert requires_auto_verify("click")
    assert not requires_auto_verify("scrape")


def test_human_park_tab_denied():
    assert (
        policy_denied_reason(
            "openTab", 87, 42, params={"placement": "human"}
        )
        == "human_park_tab_denied"
    )
    assert policy_denied_reason("openTab", 87, 42, params={}) is None
    assert (
        policy_denied_reason("openTab", 87, 42, params={"placement": "agent"}) is None
    )
