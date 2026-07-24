import asyncio

from kiku_ai.auth import ApiKeyCredential, Credential, MemoryCredentialStore, ModelAuth
from kiku_ai.providers import FakeProvider, ProviderManager


async def test_manager_resolves_provider_auth() -> None:
    manager = ProviderManager()
    manager.register(FakeProvider())

    assert await manager.resolve_auth("fake") == ModelAuth()


async def test_manager_passes_stored_credential_to_provider_auth() -> None:
    store = MemoryCredentialStore()
    credential = ApiKeyCredential(key="secret")
    await store.modify("fake", lambda _: asyncio.sleep(0, result=credential))
    auth = CapturingAuth()
    provider = FakeProvider()
    provider.auth = auth
    manager = ProviderManager(credential_store=store)
    manager.register(provider)

    result = await manager.resolve_auth("fake")

    assert auth.credential is credential
    assert result == ModelAuth(api_key="secret")


class CapturingAuth:
    def __init__(self) -> None:
        self.credential: Credential | None = None

    async def resolve(self, credential: Credential | None) -> ModelAuth | None:
        self.credential = credential
        if isinstance(credential, ApiKeyCredential):
            return ModelAuth(api_key=credential.key)
        return None
