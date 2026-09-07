from __future__ import annotations

import os

INTEGRATION_ID = "piphi-network-llm-vision"
INTEGRATION_NAME = "Piphi Network Llm Vision"
INTEGRATION_VERSION = "0.1.0"
PROJECT_KIND = "sidecar"
PROJECT_PRESET = "sidecar-worker"
PROJECT_DOMAIN = "sidecar-service"
DEFAULT_PORT = 4209


def runtime_port() -> int:
    raw_port = os.getenv("PORT", str(DEFAULT_PORT))
    try:
        return int(raw_port)
    except ValueError:
        return DEFAULT_PORT
