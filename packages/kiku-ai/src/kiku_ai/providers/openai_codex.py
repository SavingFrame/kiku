from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from kiku_ai.api import ApiAdapter, OpenAICodexResponsesAdapter
from kiku_ai.auth import CredentialStore, OpenAICodexEnvAuth, ProviderAuth
from kiku_ai.context import Context
from kiku_ai.events import AssistantMessageEvent, ErrorEvent
from kiku_ai.messages import AssistantMessage, StopReason, Usage
from kiku_ai.models import Model
from kiku_ai.providers.base import Provider
from kiku_ai.streaming import StreamOptions

_OPENAI_CODEX_PROVIDER_ID = "openai-codex"
_OPENAI_CODEX_API_ID = "openai-codex-responses"
_OPENAI_CODEX_BASE_URL = "https://chatgpt.com/backend-api"

_CODEX_CONTEXT = 272_000
_CODEX_SPARK_CONTEXT = 128_000
_CODEX_MAX_OUTPUT_TOKENS = 128_000

_MODEL_SPECS = (
    ("gpt-5.3-codex-spark", "GPT-5.3 Codex Spark", _CODEX_SPARK_CONTEXT),
    ("gpt-5.4", "GPT-5.4", _CODEX_CONTEXT),
    ("gpt-5.4-mini", "GPT-5.4 mini", _CODEX_CONTEXT),
    ("gpt-5.5", "GPT-5.5", _CODEX_CONTEXT),
    ("gpt-5.6-luna", "GPT-5.6 Luna", _CODEX_CONTEXT),
    ("gpt-5.6-sol", "GPT-5.6 Sol", _CODEX_CONTEXT),
    ("gpt-5.6-terra", "GPT-5.6 Terra", _CODEX_CONTEXT),
)

_OPENAI_CODEX_MODELS = tuple(
    Model(
        id=model_id,
        name=name,
        provider=_OPENAI_CODEX_PROVIDER_ID,
        api=_OPENAI_CODEX_API_ID,
        context_model=context_model,
        max_output_tokens=_CODEX_MAX_OUTPUT_TOKENS,
    )
    for model_id, name, context_model in _MODEL_SPECS
)


class OpenAICodexProvider(Provider):
    id = _OPENAI_CODEX_PROVIDER_ID
    name = "OpenAI Codex"
    base_url = _OPENAI_CODEX_BASE_URL
    auth: ProviderAuth = OpenAICodexEnvAuth()

    def __init__(
        self,
        *,
        credential_store: CredentialStore,
        api: ApiAdapter | None = None,
    ) -> None:
        super().__init__(credential_store=credential_store)
        self.api = api or OpenAICodexResponsesAdapter()

    def get_models(self) -> Sequence[Model]:
        return _OPENAI_CODEX_MODELS

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        async def iterator() -> AsyncIterator[AssistantMessageEvent]:
            try:
                auth = await self.resolve_auth()
            except Exception as error:
                yield _auth_error(str(error))
                return

            if auth is None:
                yield _auth_error("OpenAI Codex credentials are unavailable")
                return

            async for event in self.api.stream(
                model,
                context,
                options,
                auth=auth,
                base_url=self.base_url,
            ):
                yield event

        return iterator()


def _auth_error(message: str) -> ErrorEvent:
    error = AssistantMessage(
        timestamp=datetime.now(UTC),
        content=[],
        usage=Usage(),
        stop_reason=StopReason.ERROR,
        error_message=message,
    )
    return ErrorEvent(reason=StopReason.ERROR, error=error)


__all__ = ["OpenAICodexProvider"]
