from collections.abc import Sequence

from kiku_ai.api.fake import (
    FakeApiAdapter,
    FakeProviderState,
    FakeResponseFactory,
    FakeResponseStep,
)
from kiku_ai.auth import CredentialStore, KeylessAuth, ModelAuth, ProviderAuth
from kiku_ai.context import Context
from kiku_ai.models import Model
from kiku_ai.providers.base import Provider
from kiku_ai.streaming import AssistantMessageStream, StreamOptions


class FakeProvider(Provider):
    id = "fake"
    name = "Fake"
    base_url = "fake://"
    api: FakeApiAdapter
    auth: ProviderAuth = KeylessAuth()

    def __init__(
        self,
        responses: Sequence[FakeResponseStep] | None = None,
        models: Sequence[Model] | None = None,
        *,
        credential_store: CredentialStore,
    ) -> None:
        super().__init__(credential_store=credential_store)
        self.api = FakeApiAdapter(responses)
        self.responses = self.api.responses
        self.models = list(models or [_default_model()])
        self.state = self.api.state

    def enqueue(self, response: FakeResponseStep) -> None:
        self.api.enqueue(response)

    def get_models(self) -> Sequence[Model]:
        return self.models

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantMessageStream:
        return self.api.stream(
            model,
            context,
            options,
            auth=ModelAuth(),
            base_url=self.base_url,
        )


def _default_model() -> Model:
    return Model(
        id="fake-model",
        name="Fake Model",
        provider="fake",
        api="fake",
        context_model=128_000,
        max_output_tokens=16_384,
    )


__all__ = [
    "FakeApiAdapter",
    "FakeProvider",
    "FakeProviderState",
    "FakeResponseFactory",
    "FakeResponseStep",
]
