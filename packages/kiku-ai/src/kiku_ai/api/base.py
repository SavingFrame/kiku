from typing import Protocol

from kiku_ai.auth import ModelAuth
from kiku_ai.context import Context
from kiku_ai.models import Model
from kiku_ai.streaming import AssistantMessageStream, StreamOptions


class ApiAdapter(Protocol):
    """A wire-protocol adapter invoked with provider-resolved request inputs."""

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
        *,
        auth: ModelAuth,
        base_url: str,
    ) -> AssistantMessageStream: ...
