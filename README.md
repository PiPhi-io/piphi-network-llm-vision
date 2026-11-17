# Piphi Network Llm Vision

Generated PiPhi sidecar runtime.

## Run locally

```bash
pdm install -G dev
pdm run uvicorn piphi_network_llm_vision.main:app --reload --port 4209
pdm run pytest
pdm run python scripts/validate.py
```

The runtime listens on port `4209` by default and exposes the common PiPhi runtime route contract:

- `GET /health`
- `GET /diagnostics`
- `POST /discover`
- `POST /config`
- `POST /config/sync`
- `POST /deconfigure`
- `POST /deconfigure/{config_id}`
- `GET /state`
- `GET /contract`
- `GET /entities`
- `GET /events`
- `POST /events/device/{config_id}/example`
- `POST /telemetry/example`
- `POST /telemetry/device/{config_id}/example`
- `POST /command`

## Capability coverage and sidecar boundary

`capability-catalog.json` inventories analysis jobs, provider routing, timeline
and memory features, queueing, recovery, privacy boundaries, and parent-consumed
capabilities. Every entry is classified as implemented, planned, or excluded.
Contract tests enforce that only implemented entries are advertised.

This package is an opt-in sidecar worker, not a camera integration. Camera
integrations and automations submit explicitly authorized brokered media; the
sidecar owns bounded analysis work, provider access, backpressure, and result
delivery. It does not create camera entities, expose provider secrets or raw
media, perform autonomous device control, or enable continuous surveillance.

## Manifest

`manifest.json` is a starter manifest. Before publishing, update:

- `image`
- `version`
- capabilities and commands
- config fields and identity fields
- entity metadata

## Docker

```bash
docker build -t docker.io/piphinetwork/piphi-network-llm-vision:0.1.2 .
docker volume create piphi-llm-vision-data
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v piphi-llm-vision-data:/data/piphi \
  -p 127.0.0.1:4209:4209 docker.io/piphinetwork/piphi-network-llm-vision:0.1.2
```

The runtime and persistent idempotency ledger execute as UID/GID `10001`.
Deployments using the manifest's bind mount must provision
`/var/lib/piphi/llm-vision` for that ownership before startup.
