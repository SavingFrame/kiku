import abc
from collections.abc import Sequence

from kiku_ai.api import ApiAdapter
from kiku_ai.auth import CredentialStore, ModelAuth, ProviderAuth
from kiku_ai.context import Context
from kiku_ai.models import Model
from kiku_ai.streaming import AssistantMessageStream, StreamOptions


class Provider(abc.ABC):
    id: str
    name: str
    api: ApiAdapter
    base_url: str
    auth: ProviderAuth

    def __init__(
        self,
        credential_store: CredentialStore,
    ) -> None:
        self._credential_store = credential_store

    async def resolve_auth(self) -> ModelAuth | None:
        credential = await self._credential_store.read(self.id)
        return await self.auth.resolve(credential)

    @abc.abstractmethod
    def get_models(self) -> Sequence[Model]:
        raise NotImplementedError("You should implement it by yourself")

    def get_model(self, model_id: str) -> Model | None:
        return next(
            (model for model in self.get_models() if model.id == model_id),
            None,
        )

    @abc.abstractmethod
    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantMessageStream:
        raise NotImplementedError("You should implement it by yourself")


class ProviderAlreadyRegisteredError(ValueError):
    pass


class ProviderNotFoundError(LookupError):
    pass


class ProviderManager:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        if provider.id in self._providers:
            raise ProviderAlreadyRegisteredError(f"Provider {provider.id!r} is already registered")
        self._providers[provider.id] = provider

    def unregister(self, provider_id: str) -> None:
        if provider_id not in self._providers:
            raise ProviderNotFoundError(f"Provider {provider_id!r} is not registered")
        del self._providers[provider_id]

    def get_provider(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)

    def get_models(self, provider_id: str | None = None) -> Sequence[Model]:
        if provider_id is not None:
            provider = self._require_provider(provider_id)
            return provider.get_models()
        return [model for provider in self._providers.values() for model in provider.get_models()]

    def get_model(self, provider_id: str, model_id: str) -> Model | None:
        provider = self._require_provider(provider_id)
        return provider.get_model(model_id)

    def _require_provider(self, provider_id: str) -> Provider:
        provider = self.get_provider(provider_id)
        if provider is None:
            raise ProviderNotFoundError(f"Provider {provider_id!r} is not registered")
        return provider
