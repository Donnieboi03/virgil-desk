import pytest
from httpx import ASGITransport, AsyncClient

from desk_host.app import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_handoff_mock():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/handoff",
            json={
                "url": "https://example.com/job",
                "human_tab_id": 1,
                "window_id": 1,
                "title": "Job",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"]
    assert len(data["items"]) >= 1
