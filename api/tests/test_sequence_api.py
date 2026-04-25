"""BFF /ml/sequence/report endpoint (requires `pip install -e ./ml`)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from overfished_api.main import app


@pytest.mark.asyncio
async def test_get_sequence_demo() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ml/sequence/demo")
    if response.status_code == 503:
        pytest.skip("overfished-ml not installed: " + str(response.json()))
    assert response.status_code == 200, response.text
    assert "narration" in response.json()


@pytest.mark.asyncio
async def test_post_sequence_report_sample() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ml/sequence/report",
            json={"use_sample": True, "include_narration": True, "training": {"epochs": 1, "seq_len": 3, "hidden_dim": 8, "batch_size": 2}},
        )
    if response.status_code == 503:
        pytest.skip("overfished-ml not installed: " + str(response.json()))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rnn"]["metrics"]["top1_accuracy"] >= 0.0
    assert "narration" in body
