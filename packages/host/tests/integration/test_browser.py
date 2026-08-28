import pytest
from httpx import ASGITransport, AsyncClient

from desk_host.app import app, dispatch_browser_command
from desk_host.policy import policy_denied_reason


def test_policy_blocks_human_tab_click():
    assert (
        policy_denied_reason("click", 5, 5)
        == "human_tab_blocked"
    )


@pytest.mark.asyncio
async def test_dispatch_denied_on_human_tab():
    with pytest.raises(PermissionError):
        await dispatch_browser_command(
            {
                "command_id": "cmd_test",
                "run_id": "desk_test",
                "op": "click",
                "tab_id": 5,
                "human_tab_id": 5,
                "params": {"selector": "button"},
            }
        )


@pytest.mark.asyncio
async def test_browser_rest_endpoint_policy():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/browser",
            json={
                "run_id": "desk_test",
                "op": "click",
                "tab_id": 7,
                "human_tab_id": 7,
            },
        )
    assert r.status_code == 403
