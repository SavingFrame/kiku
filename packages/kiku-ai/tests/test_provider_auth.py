import asyncio

from kiku_ai.auth import ApiKeyCredential, Credential, MemoryCredentialStore, ModelAuth
from kiku_ai.providers import FakeProvider


async def test_provider_resolves_auth() -> None:
    provider = FakeProvider(credential_store=MemoryCredentialStore())

    assert await provider.resolve_auth() == ModelAuth()


async def test_provider_passes_stored_credential_to_auth() -> None:
    store = MemoryCredentialStore()
    credential = ApiKeyCredential(key="secret")
    await store.modify("fake", lambda _: asyncio.sleep(0, result=credential))
    auth = CapturingAuth()
    provider = FakeProvider(credential_store=store)
    provider.auth = auth

    result = await provider.resolve_auth()

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
