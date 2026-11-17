from __future__ import annotations

from typing import Any

ENDPOINTS = {
    "health": "/health",
    "diagnostics": "/diagnostics",
    "discover": "/discover",
    "entities": "/entities",
    "state": "/state",
    "config": "/config",
    "config_sync": "/config/sync",
    "deconfigure": "/deconfigure",
    "ui_config": "/ui-config",
    "events": "/events",
    "command": "/command",
}

REQUIRED_ENDPOINTS = ["health", "entities", "command", "config", "ui_config"]

CAPABILITIES: dict[str, dict[str, Any]] = {
    "connected": {
        "kind": "sensor",
        "unit": "bool"
    },
    "refresh": {
        "kind": "action"
    },
    "service_available": {
        "kind": "sensor",
        "unit": "bool"
    },
    "queue_depth": {
        "kind": "sensor",
        "unit": "jobs"
    },
    "queue_capacity": {
        "kind": "sensor",
        "unit": "jobs"
    },
    "active_job_count": {
        "kind": "sensor",
        "unit": "jobs"
    },
    "worker_count": {
        "kind": "sensor"
    },
    "jobs_completed_total": {
        "kind": "sensor",
        "unit": "jobs"
    },
    "jobs_failed_total": {
        "kind": "sensor",
        "unit": "jobs"
    },
    "job_status": {
        "kind": "sensor"
    },
    "analysis_summary": {
        "kind": "sensor"
    },
    "analysis_structured_result": {
        "kind": "sensor"
    },
    "source_camera_id": {
        "kind": "sensor"
    },
    "last_success_at": {
        "kind": "sensor"
    },
    "degraded_reason": {
        "kind": "sensor"
    },
    "analyze_image": {
        "kind": "action"
    },
    "cancel_analysis": {
        "kind": "action"
    }
}

COMMANDS: dict[str, dict[str, Any]] = {
    "refresh": {
        "description": "Refresh the device state.",
        "timeout_ms": 5000
    },
    "analyze_image": {
        "description": "Queue analysis of one PiPhi-brokered image.",
        "timeout_ms": 5000
    },
    "cancel_analysis": {
        "description": "Cancel one queued or running analysis job.",
        "timeout_ms": 5000
    }
}

CONFIG_SCHEMA: dict[str, Any] = {
    "schema": {
        "title": "Piphi Network Llm Vision Setup",
        "type": "object",
        "required": [
            "host"
        ],
        "properties": {
            "host": {
                "type": "string",
                "title": "Host"
            },
            "alias": {
                "type": "string",
                "title": "Alias"
            },
            "service_name": {
                "type": "string",
                "title": "Service Name"
            },
            "base_url": {
                "type": "string",
                "format": "uri",
                "title": "OpenAI-compatible API URL"
            },
            "api_key": {
                "type": "string",
                "title": "Provider API key"
            },
            "media_broker_url": {
                "type": "string",
                "format": "uri",
                "title": "PiPhi analysis media broker URL"
            },
            "media_broker_token": {
                "type": "string",
                "title": "Media broker token"
            },
            "queue_capacity": {
                "type": "integer",
                "minimum": 1,
                "maximum": 32,
                "default": 8,
                "title": "Maximum outstanding jobs"
            }
        }
    },
    "uiSchema": {
        "host": {
            "placeholder": "192.168.1.50"
        },
        "alias": {
            "placeholder": "Office Device"
        },
        "service_name": {
            "placeholder": "local-helper"
        },
        "api_key": {
            "ui:widget": "password"
        },
        "media_broker_token": {
            "ui:widget": "password"
        }
    }
}

FALLBACK_ENTITY: dict[str, Any] = {
    "id": "llm-vision-service",
    "name": "LLM Vision Service",
    "device_id": "llm-vision-service",
    "entity_type": "service",
    "capabilities": [
        "connected",
        "service_available",
        "queue_depth",
        "queue_capacity",
        "active_job_count",
        "worker_count",
        "jobs_completed_total",
        "jobs_failed_total",
        "job_status",
        "analysis_summary",
        "analysis_structured_result",
        "source_camera_id",
        "last_success_at",
        "degraded_reason",
        "refresh",
        "analyze_image",
        "cancel_analysis"
    ],
    "available_commands": [
        {
            "id": "refresh",
            "label": "Refresh",
            "kind": "action"
        },
        {
            "id": "analyze_image",
            "label": "Analyze brokered image",
            "kind": "action"
        },
        {
            "id": "cancel_analysis",
            "label": "Cancel analysis",
            "kind": "action"
        }
    ],
    "dashboard": {
        "allowed_widgets": [
            "tile",
            "stat",
            "button"
        ],
        "default_widget": "tile"
    }
}
