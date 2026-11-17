# Piphi Network Llm Vision

Bounded PiPhi sidecar for explicit analysis of broker-issued camera images with
an OpenAI-compatible vision provider.

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

## Analysis boundary

`analyze_image` accepts a broker media ID, source camera ID, and bounded prompt.
The sidecar constructs the broker URL from configured trusted base URLs; callers
cannot supply a URL or filesystem path. Brokered JPEG, PNG, or WebP content is
streamed with a 10 MiB limit, held only in memory, submitted to the configured
OpenAI-compatible `/chat/completions` endpoint, and discarded. State and events
contain only the job ID, camera ID, lifecycle status, bounded result, and usage.

The queue is bounded per configuration. Saturation fails closed, cancellation
interrupts the active provider request, and provider failures expose only a
sanitized error class. Arbitrary URLs/files, redirects, raw-media persistence,
provider tools, continuous surveillance, and autonomous control are rejected.

Required provider configuration is `base_url`, `api_key`, and `service_name`.
Required media configuration is `media_broker_url`; `media_broker_token` is
optional when the broker uses another internal authorization mechanism. Only
HTTPS endpoints are accepted, except loopback HTTP for local development.

## Docker

```bash
docker build -t docker.io/piphinetwork/piphi-network-llm-vision:0.1.3 .
docker volume create piphi-llm-vision-data
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v piphi-llm-vision-data:/data/piphi \
  -p 127.0.0.1:4209:4209 docker.io/piphinetwork/piphi-network-llm-vision:0.1.3
```

The runtime and persistent idempotency ledger execute as UID/GID `10001`.
Deployments using the manifest's bind mount must provision
`/var/lib/piphi/llm-vision` for that ownership before startup.
