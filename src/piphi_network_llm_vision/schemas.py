from __future__ import annotations

from piphi_runtime_kit_python import RuntimeConfig
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)


class DeviceConfig(RuntimeConfig):
    host: str
    alias: str | None = None
    api_key: SecretStr | None = None
    base_url: AnyHttpUrl | None = None
    media_broker_url: AnyHttpUrl | None = None
    media_broker_token: SecretStr | None = None
    poll_interval_seconds: int | None = None
    service_name: str = "gpt-4.1-mini"
    queue_capacity: int = Field(default=8, ge=1, le=32)
    request_timeout_seconds: float = Field(default=30, ge=1, le=120)
    max_output_tokens: int = Field(default=500, ge=32, le=4000)

    @field_validator("base_url", "media_broker_url")
    @classmethod
    def require_https_or_loopback(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is None:
            return None
        if value.scheme == "https" or value.host in {"127.0.0.1", "localhost", "::1"}:
            return value
        raise ValueError("URL must use HTTPS unless it targets loopback")


class AnalyzeImageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    media_ref: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    source_camera_id: str = Field(
        min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    prompt: str = Field(min_length=1, max_length=2000)


class CancelAnalysisArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    job_id: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]{32}$")
