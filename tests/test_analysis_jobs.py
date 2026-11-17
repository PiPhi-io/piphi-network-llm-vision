from __future__ import annotations

import asyncio
from typing import Any

import pytest

from piphi_network_llm_vision.jobs import AnalysisQueueFullError, AnalysisService
from piphi_network_llm_vision.provider import AnalysisResult
from piphi_network_llm_vision.schemas import DeviceConfig


class BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def analyze(
        self, config: DeviceConfig, media_ref: str, prompt: str
    ) -> AnalysisResult:
        assert media_ref == "broker-image-1"
        assert prompt == "Describe hazards"
        self.started.set()
        await self.release.wait()
        return AnalysisResult("No hazards detected", {"hazard": False}, 12, 4)


class FailingProvider:
    async def analyze(
        self, _config: DeviceConfig, _media_ref: str, _prompt: str
    ) -> AnalysisResult:
        raise RuntimeError("private upstream detail")


@pytest.mark.anyio
async def test_bounded_job_lifecycle_backpressure_and_sanitized_events() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    states: list[dict[str, Any]] = []
    provider = BlockingProvider()
    service = AnalysisService(
        lambda event_type, _entry, payload, _severity: events.append((event_type, payload)),
        lambda _config_id, state: states.append(state),
        provider,
        queue_capacity=1,
    )
    config = configured_device(queue_capacity=1)
    service.configure(config, {"config_id": "vision", "device_id": "vision"})

    first = await service.submit(
        "vision",
        media_ref="broker-image-1",
        source_camera_id="front-door",
        prompt="Describe hazards",
    )
    await provider.started.wait()
    assert first["status"] == "queued"
    assert "media_ref" not in first
    assert "prompt" not in first

    with pytest.raises(AnalysisQueueFullError):
        await service.submit(
            "vision",
            media_ref="broker-image-2",
            source_camera_id="front-door",
            prompt="Describe hazards",
        )
    assert events[-1][0] == "queue.saturated"

    provider.release.set()
    await asyncio.wait_for(service.queue.join(), 1)
    completed = service.jobs[first["id"]].public()
    assert completed["status"] == "completed"
    assert completed["summary"] == "No hazards detected"
    assert service.jobs[first["id"]].media_ref == ""
    assert service.jobs[first["id"]].prompt == ""
    assert [name for name, _ in events].count("analysis.completed") == 1
    assert [name for name, _ in events].count("queue.recovered") == 1
    assert all("broker-image" not in str(payload) for _, payload in events)
    assert states[-1]["jobs_completed_total"] == 1
    await service.stop()


@pytest.mark.anyio
async def test_job_state_and_cancellation_are_scoped_to_configuration() -> None:
    provider = BlockingProvider()
    service = AnalysisService(lambda *_: None, lambda *_: None, provider)
    service.configure(configured_device(), {"config_id": "vision"})
    other = configured_device().model_copy(update={"id": "other"})
    service.configure(other, {"config_id": "other"})
    job = await service.submit(
        "vision",
        media_ref="broker-image-1",
        source_camera_id="front-door",
        prompt="Describe hazards",
    )
    await provider.started.wait()

    assert service.snapshot("vision")["active_job_count"] == 1
    assert service.snapshot("other")["active_job_count"] == 0
    assert service.snapshot("other")["job_status"] is None
    with pytest.raises(KeyError, match="unknown analysis job"):
        await service.cancel("other", job["id"])

    await service.cancel("vision", job["id"])
    await asyncio.wait_for(service.queue.join(), 1)
    await service.stop()


@pytest.mark.anyio
async def test_queued_job_can_be_cancelled_without_provider_execution() -> None:
    provider = BlockingProvider()
    service = AnalysisService(lambda *_: None, lambda *_: None, provider)
    service.configure(configured_device(), {"config_id": "vision"})
    job = await service.submit(
        "vision",
        media_ref="broker-image-1",
        source_camera_id="front-door",
        prompt="Describe hazards",
    )
    cancelled = await service.cancel("vision", job["id"])
    assert cancelled["status"] == "cancelled"
    await asyncio.wait_for(service.queue.join(), 1)
    assert not provider.started.is_set()
    await service.stop()


@pytest.mark.anyio
async def test_running_job_cancellation_interrupts_provider() -> None:
    provider = BlockingProvider()
    service = AnalysisService(lambda *_: None, lambda *_: None, provider)
    service.configure(configured_device(), {"config_id": "vision"})
    job = await service.submit(
        "vision",
        media_ref="broker-image-1",
        source_camera_id="front-door",
        prompt="Describe hazards",
    )
    await provider.started.wait()
    cancelled = await service.cancel("vision", job["id"])
    assert cancelled["status"] == "cancelled"
    await asyncio.wait_for(service.queue.join(), 1)
    assert service.jobs[job["id"]].status == "cancelled"
    assert service.jobs[job["id"]].media_ref == ""
    assert service.jobs[job["id"]].prompt == ""
    assert service._worker is not None and not service._worker.done()
    await service.stop()


@pytest.mark.anyio
async def test_provider_failure_is_sanitized_and_worker_survives() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    service = AnalysisService(
        lambda event_type, _entry, payload, _severity: events.append((event_type, payload)),
        lambda *_: None,
        FailingProvider(),
    )
    service.configure(configured_device(), {"config_id": "vision"})
    job = await service.submit(
        "vision",
        media_ref="broker-image-1",
        source_camera_id="front-door",
        prompt="Describe hazards",
    )
    await asyncio.wait_for(service.queue.join(), 1)
    failed = service.jobs[job["id"]].public()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "RuntimeError"
    assert service.jobs[job["id"]].media_ref == ""
    assert service.jobs[job["id"]].prompt == ""
    assert "private upstream detail" not in str(failed)
    assert "private upstream detail" not in str(events)
    assert service._worker is not None and not service._worker.done()
    await service.stop()


def configured_device(*, queue_capacity: int = 8) -> DeviceConfig:
    return DeviceConfig(
        id="vision",
        host="provider",
        base_url="https://provider.example/v1",
        api_key="provider-secret",
        media_broker_url="https://broker.example",
        queue_capacity=queue_capacity,
    )
