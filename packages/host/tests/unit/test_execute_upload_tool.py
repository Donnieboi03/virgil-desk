"""Unit tests for host_loop upload tool schema."""

from desk_host.execute_tools import BROWSER_TOOL_NAMES, host_loop_tools


def test_upload_in_browser_tools():
    assert "upload" in BROWSER_TOOL_NAMES
    assert "set_files" in BROWSER_TOOL_NAMES


def test_host_loop_tools_include_upload():
    names = {t["function"]["name"] for t in host_loop_tools()}
    assert "upload" in names
    assert "fill" in names
