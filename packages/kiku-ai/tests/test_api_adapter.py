from kiku_ai import AssistantMessageStream, Context, Model, StreamOptions
from kiku_ai.api import ApiAdapter
from kiku_ai.auth import ModelAuth


class RecordingAdapter:
    def __init__(self) -> None:
        self.request: tuple[Model, Context, StreamOptions | None, ModelAuth, str] | None = None
        self.response = AssistantMessageStream()

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
        *,
        auth: ModelAuth,
        base_url: str,
    ) -> AssistantMessageStream:
        self.request = (model, context, options, auth, base_url)
        return self.response


def invoke_adapter(
    adapter: ApiAdapter,
    model: Model,
    context: Context,
    options: StreamOptions | None,
    auth: ModelAuth,
    base_url: str,
) -> AssistantMessageStream:
    return adapter.stream(model, context, options, auth=auth, base_url=base_url)


def test_adapter_receives_provider_resolved_request_inputs() -> None:
    adapter = RecordingAdapter()
    model = Model(
        id="test-model",
        name="Test Model",
        provider="test-provider",
        api="test-api",
        context_model=128_000,
        max_output_tokens=16_384,
    )
    context = Context(messages=[])
    options = StreamOptions(session_id="session-1")
    auth = ModelAuth(
        api_key="secret",
        headers={"chatgpt-account-id": "account-1"},
    )
    base_url = "https://example.test"

    stream = invoke_adapter(adapter, model, context, options, auth, base_url)

    assert stream is adapter.response
    assert adapter.request == (model, context, options, auth, base_url)
