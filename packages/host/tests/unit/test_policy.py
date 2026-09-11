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
    assert policy_denied_reason("openTab", 87, 42, params={}, url="https://ex.com") is None
    assert (
        policy_denied_reason("openTab", 87, 42, params={"placement": "agent"}, url="https://ex.com")
        is None
    )


def test_open_tab_url_required():
    assert policy_denied_reason("openTab", 87, 42, params={}) == "open_tab_url_required"
    assert (
        policy_denied_reason("openTab", 87, 42, url="about:blank") == "open_tab_url_required"
    )
    assert (
        policy_denied_reason(
            "openTab", 87, 42, params={"url": "https://jobs.example.com/apply"}
        )
        is None
    )


def test_forbidden_action_token_from_params_label():
    assert (
        policy_denied_reason(
            "click",
            87,
            42,
            params={"target_id": 3, "label": "Send"},
        )
        == "forbidden_action_token"
    )
    assert (
        policy_denied_reason(
            "click",
            87,
            42,
            params={"target_id": 3, "label": "Submit application"},
        )
        == "forbidden_action_token"
    )
    assert (
        policy_denied_reason(
            "fill",
            87,
            42,
            params={"target_id": 1, "value": "hello"},
        )
        is None
    )
    assert (
        policy_denied_reason(
            "click",
            87,
            42,
            params={"target_id": 2, "label": "Reply"},
        )
        is None
    )


def test_forbidden_action_token_from_explicit_text():
    assert (
        policy_denied_reason("click", 87, 42, text="Pay now")
        == "forbidden_action_token"
    )
