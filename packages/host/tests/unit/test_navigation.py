from desk_host.navigation import choose_navigation_op, normalize_browser_command


def test_duplicate_same_path():
    assert (
        choose_navigation_op(
            "https://example.com/job/1?q=a",
            "https://example.com/job/1#x",
        )
        == "duplicateTab"
    )


def test_open_different_host():
    assert (
        choose_navigation_op("https://example.com/a", "https://other.com/a")
        == "openTab"
    )


def test_normalize_navigate():
    cmd = normalize_browser_command(
        {
            "op": "navigate",
            "url": "https://example.com/page",
            "handoff_url": "https://example.com/page",
        }
    )
    assert cmd["op"] == "duplicateTab"


def test_normalize_promotes_params_url():
    cmd = normalize_browser_command(
        {
            "op": "openTab",
            "params": {"url": "https://jobs.example.com/apply"},
            "handoff_url": "https://mail.google.com/mail/u/0/",
        }
    )
    assert cmd["url"] == "https://jobs.example.com/apply"
    assert cmd["op"] == "openTab"
