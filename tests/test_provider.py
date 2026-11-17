from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from piphi_network_llm_vision.provider import (
    MAX_MEDIA_BYTES,
    OpenAICompatibleVisionProvider,
)
from piphi_network_llm_vision.schemas import AnalyzeImageArgs, DeviceConfig


@pytest.mark.anyio
async def test_openai_compatible_provider_uses_only_brokered_media_and_redacts_secrets() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "broker.example":
            assert request.url.path == "/v1/analysis-media/image-123"
            assert request.headers["authorization"] == "Bearer broker-secret"
            return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"image")
        assert request.url == httpx.URL("https://provider.example/v1/chat/completions")
        assert request.headers["authorization"] == "Bearer provider-secret"
        body = json.loads(request.content)
        assert body["messages"][0]["content"][1]["image_url"]["url"].startswith(
            "data:image/jpeg;base64,"
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"person": false}'}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3},
            },
        )

    provider = OpenAICompatibleVisionProvider(httpx.MockTransport(handler))
    config = DeviceConfig(
        id="vision",
        host="provider",
        base_url="https://provider.example/v1",
        api_key="provider-secret",
        media_broker_url="https://broker.example",
        media_broker_token="broker-secret",
    )
    result = await provider.analyze(config, "image-123", "Describe the image")
    assert result.summary == '{"person": false}'
    assert result.structured_result == {"person": False}
    assert result.input_tokens == 8
    assert result.output_tokens == 3
    assert "provider-secret" not in repr(result)
    assert "broker-secret" not in repr(result)
    assert len(requests) == 2


def test_provider_urls_require_https_except_loopback() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        DeviceConfig(id="vision", host="provider", base_url="http://provider.example/v1")
    assert DeviceConfig(id="vision", host="provider", base_url="http://127.0.0.1:11434/v1")


@pytest.mark.parametrize(
    "media_ref",
    ["https://camera.example/private.jpg", "../../private.jpg", "/var/lib/camera.jpg"],
)
def test_analysis_input_rejects_urls_and_filesystem_paths(media_ref: str) -> None:
    with pytest.raises(ValidationError):
        AnalyzeImageArgs(
            media_ref=media_ref,
            source_camera_id="front-door",
            prompt="Describe the image",
        )


@pytest.mark.anyio
async def test_provider_rejects_oversized_broker_media_before_provider_request() -> None:
    provider_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal provider_called
        if request.url.host == "broker.example":
            return httpx.Response(
                200,
                headers={
                    "content-type": "image/jpeg",
                    "content-length": str(MAX_MEDIA_BYTES + 1),
                },
                content=b"",
            )
        provider_called = True
        return httpx.Response(500)

    provider = OpenAICompatibleVisionProvider(httpx.MockTransport(handler))
    config = DeviceConfig(
        id="vision",
        host="provider",
        base_url="https://provider.example/v1",
        api_key="provider-secret",
        media_broker_url="https://broker.example",
    )
    with pytest.raises(ValueError, match="10 MiB"):
        await provider.analyze(config, "image-123", "Describe the image")
    assert provider_called is False
