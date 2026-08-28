import pytest
from httpx import ASGITransport, AsyncClient

from desk_host.app import app


@pytest.mark.asyncio
async def test_handoff_then_accept_calendar_proposal():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        handoff = await client.post(
            "/v1/handoff",
            json={
                "url": "https://example.com/calendar",
                "human_tab_id": 9,
                "window_id": 1,
                "title": "Schedule",
            },
        )
        assert handoff.status_code == 200
        data = handoff.json()
        waiting = [i for i in data["items"] if i.get("column") == "waiting"]
        assert waiting, "mock backend should propose a calendar slot"
        item = waiting[0]
        prop = item["proposals"][0]
        assert prop["kind"] == "calendar_slot"

        accept = await client.post(
            f"/v1/items/{item['id']}/accept",
            json={
                "run_id": data["run_id"],
                "proposal_id": prop["id"],
                "work_item_id": item["id"],
            },
        )
    assert accept.status_code == 200
    body = accept.json()
    assert body["ok"] is True
    assert body["committed"]["kind"] == "calendar_slot"
    assert body["committed"]["status"] == "booked_stub"


@pytest.mark.asyncio
async def test_deny_proposal():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        handoff = await client.post(
            "/v1/handoff",
            json={
                "url": "https://example.com/x",
                "human_tab_id": 2,
                "window_id": 1,
            },
        )
        data = handoff.json()
        waiting = [i for i in data["items"] if i.get("column") == "waiting"][0]
        prop = waiting["proposals"][0]
        deny = await client.post(
            f"/v1/items/{waiting['id']}/deny",
            json={
                "run_id": data["run_id"],
                "proposal_id": prop["id"],
                "reason": "conflict",
            },
        )
    assert deny.status_code == 200
    assert deny.json()["status"] == "denied"
