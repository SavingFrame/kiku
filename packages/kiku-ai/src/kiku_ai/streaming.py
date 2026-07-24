from enum import StrEnum

from pydantic import BaseModel


class ReasoningLevel(StrEnum):
    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class StreamOptions(BaseModel):
    temperature: float | None = None
    max_output_tokens: int | None = None
    reasoning: ReasoningLevel | str | None = None
    timeout_seconds: float | None = None
    max_retries: int | None = None
    max_retry_delay_seconds: float | None = None
    headers: dict[str, str | None] | None = None
    session_id: str | None = None
