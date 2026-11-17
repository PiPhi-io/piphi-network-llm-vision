from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException
from piphi_runtime_kit_python import (
    AutomationRegistry,
    SQLiteAutomationIdempotencyStore,
    build_local_event_record,
    build_runtime_identity,
    create_runtime_starter,
)
from pydantic import ValidationError

from .contract import CAPABILITIES, COMMANDS
from .jobs import AnalysisNotConfiguredError, AnalysisQueueFullError, AnalysisService
from .schemas import AnalyzeImageArgs, CancelAnalysisArgs, DeviceConfig
from .settings import INTEGRATION_ID, INTEGRATION_NAME, INTEGRATION_VERSION

starter = create_runtime_starter(
    integration_id=INTEGRATION_ID,
    integration_name=INTEGRATION_NAME,
    version=INTEGRATION_VERSION,
)
runtime = starter.runtime
registry = starter.registry
telemetry = starter.telemetry_client
config_sync = starter.config_sync
automations = AutomationRegistry(
    idempotency_store=SQLiteAutomationIdempotencyStore(
        os.getenv("PIPHI_AUTOMATION_LEDGER_PATH", "./data/automation-actions.sqlite3")
    )
)

capabilities = CAPABILITIES
commands = COMMANDS


def make_entry(config: DeviceConfig) -> dict[str, Any]:
    identity = build_runtime_identity(config, integration_id=INTEGRATION_ID)
    return {
        **identity,
        "host": config.host,
        "alias": config.alias,
    }


def append_runtime_event(
    event_type: str,
    device: dict[str, Any],
    payload: dict[str, Any] | None = None,
    severity: str = "info",
) -> dict[str, Any]:
    event = build_local_event_record(
        event_type=event_type,
        device=device,
        payload=payload or {},
        source=INTEGRATION_ID,
        severity=severity,
    )
    registry.append_event(event)
    return event


def update_analysis_state(config_id: str, snapshot: dict[str, Any]) -> None:
    entry = registry.get(config_id)
    if entry is None:
        return
    registry.update_state(
        config_id,
        {
            "connected": True,
            "provider_configured": (
                config_id in analysis.configs
                and analysis.configs[config_id].base_url is not None
                and analysis.configs[config_id].media_broker_url is not None
                and analysis.configs[config_id].api_key is not None
            ),
            **snapshot,
            "config_id": entry["config_id"],
        },
        device_id=entry["device_id"],
    )


analysis = AnalysisService(append_runtime_event, update_analysis_state)


def get_entry_or_404(config_id: str) -> dict[str, Any]:
    entry = registry.get(config_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown config_id={config_id}")
    return entry


async def apply_config(config: DeviceConfig) -> None:
    entry = make_entry(config)
    registry.set(config.id, entry)
    analysis.configure(config, entry)
    append_runtime_event(
        "runtime.config.applied",
        entry,
        {"host": config.host, "alias": config.alias},
    )


async def remove_config(config_id: str) -> bool:
    await analysis.remove(config_id)
    entry = registry.remove(config_id)
    if entry is None:
        return False
    append_runtime_event(
        "runtime.config.removed",
        entry,
        {"host": entry.get("host"), "alias": entry.get("alias")},
    )
    return True


def _register_automation_actions() -> None:
    def resolve_config_id(request: Any) -> str:
        target = request.target if isinstance(request.target, dict) else {}
        config_id = str(request.config_id or target.get("config_id") or "")
        if not config_id or registry.get(config_id) is None:
            raise HTTPException(status_code=404, detail="unknown configuration")
        return config_id

    def refresh_handler(request: Any) -> dict[str, Any]:
        config_id = resolve_config_id(request)
        return {
            "command": "refresh",
            "config_id": config_id,
            **analysis.snapshot(config_id),
        }

    async def analyze_handler(request: Any) -> dict[str, Any]:
        config_id = resolve_config_id(request)
        try:
            args = AnalyzeImageArgs.model_validate(request.args)
            return await analysis.submit(config_id, **args.model_dump())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid analysis request") from exc
        except AnalysisQueueFullError as exc:
            raise HTTPException(status_code=429, detail="analysis queue is full") from exc
        except AnalysisNotConfiguredError as exc:
            raise HTTPException(status_code=409, detail="analysis provider is not configured") from exc

    async def cancel_handler(request: Any) -> dict[str, Any]:
        config_id = resolve_config_id(request)
        try:
            args = CancelAnalysisArgs.model_validate(request.args)
            return await analysis.cancel(config_id, args.job_id)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid cancellation request") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown analysis job") from exc

    automations.action("refresh", label="Refresh service state")(refresh_handler)
    automations.action("analyze_image", label="Analyze brokered image")(analyze_handler)
    automations.action("cancel_analysis", label="Cancel analysis")(cancel_handler)


_register_automation_actions()
