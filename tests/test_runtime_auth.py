from __future__ import annotations

import httpx
import pytest

from piphi_network_llm_vision.main import app


@pytest.mark.anyio
async def test_operational_routes_fail_closed_without_runtime_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PIPHI_ALLOW_UNAUTHENTICATED")
    monkeypatch.delenv("PIPHI_INTEGRATION_INTERNAL_TOKEN", raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/entities")).status_code == 503


@pytest.mark.anyio
async def test_runtime_token_protects_operational_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPHI_ALLOW_UNAUTHENTICATED")
    monkeypatch.setenv("PIPHI_INTEGRATION_INTERNAL_TOKEN", "runtime-secret")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/entities")).status_code == 401
        assert (
            await client.get(
                "/entities", headers={"X-PiPhi-Integration-Token": "runtime-secret"}
            )
        ).status_code == 200
