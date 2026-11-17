from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from .schemas import DeviceConfig

MAX_MEDIA_BYTES = 10 * 1024 * 1024
SUPPORTED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    summary: str
    structured_result: dict[str, Any] | None
    input_tokens: int | None
    output_tokens: int | None


class VisionProvider(Protocol):
    async def analyze(self, config: DeviceConfig, media_ref: str, prompt: str) -> AnalysisResult: ...


class OpenAICompatibleVisionProvider:
    """Fetch broker-owned media and submit it to an OpenAI-compatible endpoint."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def analyze(self, config: DeviceConfig, media_ref: str, prompt: str) -> AnalysisResult:
        if config.base_url is None or config.media_broker_url is None or config.api_key is None:
            raise ValueError("provider base URL, media broker URL, and API key are required")
        timeout = httpx.Timeout(config.request_timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            async with client.stream(
                "GET",
                f"{str(config.media_broker_url).rstrip('/')}/v1/analysis-media/{quote(media_ref, safe='')}",
                headers=_broker_headers(config),
            ) as media:
                media.raise_for_status()
                content_type = media.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in SUPPORTED_MEDIA_TYPES:
                    raise ValueError("media broker returned an unsupported image type")
                declared_size = int(media.headers.get("content-length", "0") or "0")
                if declared_size > MAX_MEDIA_BYTES:
                    raise ValueError("brokered image exceeds the 10 MiB limit")
                chunks: list[bytes] = []
                received = 0
                async for chunk in media.aiter_bytes():
                    received += len(chunk)
                    if received > MAX_MEDIA_BYTES:
                        raise ValueError("brokered image exceeds the 10 MiB limit")
                    chunks.append(chunk)
            image_url = (
                f"data:{content_type};base64,{base64.b64encode(b''.join(chunks)).decode('ascii')}"
            )
            response = await client.post(
                f"{str(config.base_url).rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.service_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ],
                    "max_tokens": config.max_output_tokens,
                },
            )
            response.raise_for_status()
        payload = response.json()
        summary = str(payload["choices"][0]["message"]["content"]).strip()
        if not summary:
            raise ValueError("provider returned an empty analysis")
        summary = summary[:4000]
        structured: dict[str, Any] | None = None
        try:
            candidate = json.loads(summary)
            if isinstance(candidate, dict):
                structured = candidate
        except json.JSONDecodeError:
            pass
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return AnalysisResult(
            summary=summary,
            structured_result=structured,
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
        )


def _broker_headers(config: DeviceConfig) -> dict[str, str]:
    if config.media_broker_token is None:
        return {}
    return {"Authorization": f"Bearer {config.media_broker_token.get_secret_value()}"}


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
