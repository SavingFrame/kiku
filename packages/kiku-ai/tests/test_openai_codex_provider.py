from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from kiku_ai import (
    AssistantMessage,
    AssistantMessageEvent,
    Context,
    DoneEvent,
    ErrorEvent,
    Model,
    StartEvent,
    StopReason,
    StreamOptions,
    TextContent,
    Usage,
)
from kiku_ai.api import ApiAdapter, OpenAICodexResponsesAdapter
from kiku_ai.auth import Credential, CredentialUpdate, ModelAuth, OpenAICodexEnvAuth
from kiku_ai.providers import OpenAICodexProvider


def _message(*, terminal: bool = False) -> AssistantMessage:
    return AssistantMessage(
        timestamp=datetime.now(UTC),
        content=[TextContent(content="hello")] if terminal else [],
        usage=Usage(),
        stop_reason=StopReason.STOP if terminal else None,
    )


def _events() -> list[AssistantMessageEvent]:
    return [
        StartEvent(partial=_message()),
        DoneEvent(reason=StopReason.STOP, message=_message(terminal=True)),
    ]


class RecordingCredentialStore:
    def __init__(self) -> None:
        self.read_provider_ids: list[str] = []

    async def read(self, provider_id: str) -> Credential | None:
        self.read_provider_ids.append(provider_id)
        return None

    async def modify(
        self,
        provider_id: str,
        update: CredentialUpdate,
    ) -> Credential | None:
        del provider_id
        return await update(None)

    async def delete(self, provider_id: str) -> None:
        del provider_id


class RecordingAdapter:
    def __init__(self, events: Sequence[AssistantMessageEvent]) -> None:
        self.events = events
        self.calls = 0
        self.model: Model | None = None
        self.context: Context | None = None
        self.options: StreamOptions | None = None
        self.auth: ModelAuth | None = None
        self.base_url: str | None = None

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
        *,
        auth: ModelAuth,
        base_url: str,
    ) -> AsyncIterator[AssistantMessageEvent]:
        self.calls += 1
        self.model = model
        self.context = context
        self.options = options
        self.auth = auth
        self.base_url = base_url

        async def iterator() -> AsyncIterator[AssistantMessageEvent]:
            for event in self.events:
                yield event

        return iterator()


def _provider(
    store: RecordingCredentialStore,
    adapter: ApiAdapter | None = None,
    env: dict[str, str] | None = None,
) -> OpenAICodexProvider:
    provider = OpenAICodexProvider(credential_store=store, api=adapter)
    provider.auth = OpenAICodexEnvAuth(
        env
        if env is not None
        else {
            "OPENAI_CODEX_ACCESS_TOKEN": "access-token",
            "OPENAI_CODEX_ACCOUNT_ID": "account-id",
        }
    )
    return provider


def test_provider_metadata_and_default_adapter() -> None:
    provider = OpenAICodexProvider(credential_store=RecordingCredentialStore())

    assert provider.id == "openai-codex"
    assert provider.name == "OpenAI Codex"
    assert provider.base_url == "https://chatgpt.com/backend-api"
    assert isinstance(provider.api, OpenAICodexResponsesAdapter)


def test_models_match_current_pi_codex_catalog() -> None:
    provider = OpenAICodexProvider(credential_store=RecordingCredentialStore())
    models = provider.get_models()

    assert [(model.id, model.context_model) for model in models] == [
        ("gpt-5.3-codex-spark", 128_000),
        ("gpt-5.4", 272_000),
        ("gpt-5.4-mini", 272_000),
        ("gpt-5.5", 272_000),
        ("gpt-5.6-luna", 272_000),
        ("gpt-5.6-sol", 272_000),
        ("gpt-5.6-terra", 272_000),
    ]
    assert all(model.provider == "openai-codex" for model in models)
    assert all(model.api == "openai-codex-responses" for model in models)
    assert all(model.max_output_tokens == 128_000 for model in models)


async def test_resolves_credentials_and_delegates_to_adapter() -> None:
    store = RecordingCredentialStore()
    adapter = RecordingAdapter(_events())
    provider = _provider(store, adapter)
    model = provider.get_models()[0]
    context = Context(messages=[])
    options = StreamOptions(session_id="session-id")

    events = [event async for event in provider.stream(model, context, options)]

    assert store.read_provider_ids == ["openai-codex"]
    assert adapter.calls == 1
    assert adapter.model is model
    assert adapter.context is context
    assert adapter.options is options
    assert adapter.auth == ModelAuth(
        api_key="access-token",
        headers={"chatgpt-account-id": "account-id"},
    )
    assert adapter.base_url == "https://chatgpt.com/backend-api"
    assert events == adapter.events


async def test_unavailable_credentials_become_normalized_error() -> None:
    store = RecordingCredentialStore()
    adapter = RecordingAdapter(_events())
    provider = _provider(store, adapter, env={})

    events = [event async for event in provider.stream(provider.get_models()[0], Context(messages=[]))]

    assert adapter.calls == 0
    assert len(events) == 1
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.reason == StopReason.ERROR
    assert error.error.stop_reason == StopReason.ERROR
    assert error.error.error_message == "OpenAI Codex credentials are unavailable"


async def test_invalid_credentials_become_normalized_error() -> None:
    store = RecordingCredentialStore()
    adapter = RecordingAdapter(_events())
    provider = _provider(store, adapter, env={"OPENAI_CODEX_ACCESS_TOKEN": "access-token"})

    events = [event async for event in provider.stream(provider.get_models()[0], Context(messages=[]))]

    assert adapter.calls == 0
    assert len(events) == 1
    error = events[0]
    assert isinstance(error, ErrorEvent)
    assert error.error.stop_reason == StopReason.ERROR
    assert error.error.error_message is not None
    assert "OPENAI_CODEX_ACCOUNT_ID" in error.error.error_message


async def test_stream_execution_is_lazy() -> None:
    store = RecordingCredentialStore()
    adapter = RecordingAdapter(_events())
    provider = _provider(store, adapter)

    stream = provider.stream(provider.get_models()[0], Context(messages=[]))

    assert store.read_provider_ids == []
    assert adapter.calls == 0

    first = await anext(stream)

    assert isinstance(first, StartEvent)
    assert store.read_provider_ids == ["openai-codex"]
    assert adapter.calls == 1
    await stream.aclose()
