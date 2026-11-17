from __future__ import annotations

import asyncio

import httpx
import pytest

from piphi_network_llm_vision.main import app
from piphi_network_llm_vision.provider import AnalysisResult
from piphi_network_llm_vision.schemas import DeviceConfig
from piphi_network_llm_vision.state import analysis


class CancellableProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def analyze(
        self, _config: DeviceConfig, _media_ref: str, _prompt: str
    ) -> AnalysisResult:
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


@pytest.mark.anyio
async def test_analysis_and_cancellation_actions_execute_through_runtime_contract() -> None:
    provider = CancellableProvider()
    original_provider = analysis.provider
    analysis.provider = provider
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            configured = await client.post(
                "/config",
                json={
                    "id": "vision-e2e",
                    "host": "provider",
                    "base_url": "https://provider.example/v1",
                    "api_key": "provider-secret",
                    "media_broker_url": "https://broker.example",
                    "queue_capacity": 2,
                },
            )
            assert configured.status_code == 200
            submitted = await client.post(
                "/command",
                json={
                    "contract_version": "automation.runtime.command.v1",
                    "command": "analyze_image",
                    "config_id": "vision-e2e",
                    "params": {
                        "media_ref": "broker-image-1",
                        "source_camera_id": "front-door",
                        "prompt": "Describe hazards",
                    },
                },
            )
            assert submitted.status_code == 200
            assert submitted.json()["status"] == "queued"
            job_id = submitted.json()["id"]
            await provider.started.wait()

            cancelled = await client.post(
                "/command",
                json={
                    "contract_version": "automation.runtime.command.v1",
                    "command": "cancel_analysis",
                    "config_id": "vision-e2e",
                    "params": {"job_id": job_id},
                },
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            await asyncio.wait_for(provider.cancelled.wait(), 1)
            await asyncio.wait_for(analysis.queue.join(), 1)
            events = (await client.get("/events")).json()["events"]
            assert any(item["event_type"] == "analysis.queued" for item in events)
            assert any(item["event_type"] == "analysis.cancelled" for item in events)
            health = (await client.get("/health")).json()
            assert health["metadata"] == {"scope": "liveness"}
            assert "vision-e2e" not in str(health)
        finally:
            await client.post("/deconfigure/vision-e2e")
            await analysis.stop()
            analysis.provider = original_provider
