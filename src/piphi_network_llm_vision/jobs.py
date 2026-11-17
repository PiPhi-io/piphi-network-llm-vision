from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .provider import OpenAICompatibleVisionProvider, VisionProvider
from .schemas import DeviceConfig

EventCallback = Callable[[str, dict[str, Any], dict[str, Any], str], Any]
StateCallback = Callable[[str, dict[str, Any]], None]
MAX_JOB_HISTORY = 256


@dataclass(slots=True)
class AnalysisJob:
    id: str
    config_id: str
    source_camera_id: str
    media_ref: str
    prompt: str
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    summary: str | None = None
    structured_result: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("media_ref")
        value.pop("prompt")
        return value


class AnalysisQueueFullError(RuntimeError):
    pass


class AnalysisNotConfiguredError(RuntimeError):
    pass


class AnalysisService:
    def __init__(
        self,
        event_callback: EventCallback,
        state_callback: StateCallback,
        provider: VisionProvider | None = None,
        *,
        queue_capacity: int = 16,
    ) -> None:
        self._event = event_callback
        self._state = state_callback
        self.provider = provider or OpenAICompatibleVisionProvider()
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_capacity)
        self.configs: dict[str, DeviceConfig] = {}
        self.entries: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, AnalysisJob] = {}
        self._worker: asyncio.Task[None] | None = None
        self._active_job_id: str | None = None
        self._active_provider_task: asyncio.Task[Any] | None = None
        self._saturated_configs: set[str] = set()

    def configure(self, config: DeviceConfig, entry: dict[str, Any]) -> None:
        self.configs[config.id] = config
        self.entries[config.id] = entry
        self._publish(config.id)

    async def remove(self, config_id: str) -> None:
        for job in self.jobs.values():
            if job.config_id == config_id and job.status in {"queued", "running"}:
                await self.cancel(config_id, job.id)
        self.configs.pop(config_id, None)
        self.entries.pop(config_id, None)

    async def submit(
        self,
        config_id: str,
        *,
        media_ref: str,
        source_camera_id: str,
        prompt: str,
    ) -> dict[str, Any]:
        config = self.configs.get(config_id)
        if config is None:
            raise KeyError("unknown configuration")
        if config.base_url is None or config.media_broker_url is None or config.api_key is None:
            raise AnalysisNotConfiguredError("vision provider and media broker are not configured")
        outstanding = sum(
            job.config_id == config_id and job.status in {"queued", "running"}
            for job in self.jobs.values()
        )
        if self.queue.full() or outstanding >= config.queue_capacity:
            self._saturated_configs.add(config_id)
            self._emit("queue.saturated", config_id, {"queue_depth": self.queue.qsize()}, "warning")
            raise AnalysisQueueFullError("analysis queue is full")
        self._prune_history()
        job = AnalysisJob(
            id=uuid4().hex,
            config_id=config_id,
            source_camera_id=source_camera_id,
            media_ref=media_ref,
            prompt=prompt,
            status="queued",
            created_at=_now(),
        )
        self.jobs[job.id] = job
        self.queue.put_nowait(job.id)
        self._emit("analysis.queued", config_id, _event_payload(job), "info")
        self._publish(config_id)
        self._ensure_worker()
        return job.public()

    async def cancel(self, config_id: str, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if job is None or job.config_id != config_id:
            raise KeyError("unknown analysis job")
        if job.status not in {"queued", "running"}:
            return job.public()
        job.status = "cancelled"
        job.completed_at = _now()
        job.media_ref = ""
        job.prompt = ""
        if self._active_job_id == job.id and self._active_provider_task is not None:
            self._active_provider_task.cancel()
        self._emit("analysis.cancelled", job.config_id, _event_payload(job), "info")
        self._publish(job.config_id)
        return job.public()

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        self._active_job_id = None
        self._active_provider_task = None

    def snapshot(self, config_id: str | None = None) -> dict[str, Any]:
        jobs = [
            job for job in self.jobs.values() if config_id is None or job.config_id == config_id
        ]
        queued = sum(job.status == "queued" for job in jobs)
        running = sum(job.status == "running" for job in jobs)
        latest = jobs[-1] if jobs else None
        config = self.configs.get(config_id) if config_id is not None else None
        return {
            "service_available": self._is_configured(config)
            if config_id is not None
            else any(self._is_configured(item) for item in self.configs.values()),
            "queue_depth": queued,
            "queue_capacity": config.queue_capacity if config is not None else self.queue.maxsize,
            "active_job_count": running,
            "worker_count": int(self._worker is not None and not self._worker.done()),
            "jobs_completed_total": sum(job.status == "completed" for job in jobs),
            "jobs_failed_total": sum(job.status == "failed" for job in jobs),
            "job_status": latest.status if latest else None,
            "analysis_summary": latest.summary if latest else None,
            "analysis_structured_result": latest.structured_result if latest else None,
            "source_camera_id": latest.source_camera_id if latest else None,
            "last_success_at": (
                latest.completed_at if latest is not None and latest.status == "completed" else None
            ),
            "degraded_reason": "analysis_failed" if latest and latest.status == "failed" else None,
        }

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="llm-vision-analysis-worker")

    async def _run(self) -> None:
        while True:
            job_id = await self.queue.get()
            job = self.jobs[job_id]
            try:
                if job.status == "cancelled":
                    continue
                config = self.configs.get(job.config_id)
                if config is None:
                    job.status = "cancelled"
                    job.completed_at = _now()
                    continue
                self._active_job_id = job.id
                job.status = "running"
                job.started_at = _now()
                self._emit("analysis.started", job.config_id, _event_payload(job), "info")
                self._publish(job.config_id)
                self._active_provider_task = asyncio.create_task(
                    self.provider.analyze(config, job.media_ref, job.prompt),
                    name=f"llm-vision-provider:{job.id}",
                )
                result = await self._active_provider_task
                if job.status == "cancelled":
                    continue
                job.status = "completed"
                job.completed_at = _now()
                job.summary = result.summary
                job.structured_result = result.structured_result
                job.input_tokens = result.input_tokens
                job.output_tokens = result.output_tokens
                self._emit("analysis.completed", job.config_id, _event_payload(job), "info")
            except asyncio.CancelledError:
                if job.status != "cancelled":
                    raise
            # Provider adapters are an extension seam; an unexpected adapter failure
            # must fail one job rather than terminate the only queue worker.
            except Exception as exc:  # noqa: BLE001
                job.status = "failed"
                job.completed_at = _now()
                job.error_code = type(exc).__name__
                self._emit("analysis.failed", job.config_id, _event_payload(job), "warning")
            finally:
                if job.status in {"completed", "failed", "cancelled"}:
                    job.media_ref = ""
                    job.prompt = ""
                self._active_job_id = None
                self._active_provider_task = None
                self.queue.task_done()
                self._publish(job.config_id)
                for saturated_config_id in tuple(self._saturated_configs):
                    config = self.configs.get(saturated_config_id)
                    outstanding = sum(
                        candidate.config_id == saturated_config_id
                        and candidate.status in {"queued", "running"}
                        for candidate in self.jobs.values()
                    )
                    if not self.queue.full() and (
                        config is None or outstanding < config.queue_capacity
                    ):
                        self._saturated_configs.discard(saturated_config_id)
                        self._emit(
                            "queue.recovered",
                            saturated_config_id,
                            {"queue_depth": self.queue.qsize()},
                            "info",
                        )

    def _emit(self, event_type: str, config_id: str, payload: dict[str, Any], severity: str) -> None:
        entry = self.entries.get(config_id)
        if entry is not None:
            self._event(event_type, entry, payload, severity)

    def _publish(self, config_id: str) -> None:
        self._state(config_id, self.snapshot(config_id))

    def _prune_history(self) -> None:
        if len(self.jobs) < MAX_JOB_HISTORY:
            return
        for job_id, job in tuple(self.jobs.items()):
            if job.status not in {"queued", "running"}:
                self.jobs.pop(job_id)
                if len(self.jobs) < MAX_JOB_HISTORY:
                    return

    @staticmethod
    def _is_configured(config: DeviceConfig | None) -> bool:
        return bool(
            config is not None
            and config.base_url is not None
            and config.media_broker_url is not None
            and config.api_key is not None
        )


def _event_payload(job: AnalysisJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": job.status,
        "source_camera_id": job.source_camera_id,
        "error_code": job.error_code,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
