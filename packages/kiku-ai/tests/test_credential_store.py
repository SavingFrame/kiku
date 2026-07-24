import asyncio

from kiku_ai.auth import ApiKeyCredential, MemoryCredentialStore, OAuthCredential


async def test_reads_missing_credential() -> None:
    store = MemoryCredentialStore()

    assert await store.read("openai") is None


async def test_stores_and_replaces_credential() -> None:
    store = MemoryCredentialStore()
    first = ApiKeyCredential(key="first")
    second = ApiKeyCredential(key="second")

    assert await store.modify("openai", lambda _: asyncio.sleep(0, result=first)) is first
    assert await store.modify("openai", lambda _: asyncio.sleep(0, result=second)) is second
    assert await store.read("openai") is second


async def test_none_update_leaves_credential_unchanged() -> None:
    store = MemoryCredentialStore()
    credential = ApiKeyCredential(key="secret")
    await store.modify("openai", lambda _: asyncio.sleep(0, result=credential))

    result = await store.modify("openai", lambda _: asyncio.sleep(0, result=None))

    assert result is credential
    assert await store.read("openai") is credential


async def test_deletes_credential() -> None:
    store = MemoryCredentialStore()
    credential = ApiKeyCredential(key="secret")
    await store.modify("openai", lambda _: asyncio.sleep(0, result=credential))

    await store.delete("openai")

    assert await store.read("openai") is None


async def test_serializes_updates_for_the_same_provider() -> None:
    store = MemoryCredentialStore()
    await store.modify(
        "openai",
        lambda _: asyncio.sleep(0, result=ApiKeyCredential(key="0")),
    )

    async def increment(current: ApiKeyCredential | OAuthCredential | None):
        assert isinstance(current, ApiKeyCredential)
        value = int(current.key)
        await asyncio.sleep(0)
        return ApiKeyCredential(key=str(value + 1))

    await asyncio.gather(*(store.modify("openai", increment) for _ in range(10)))

    assert await store.read("openai") == ApiKeyCredential(key="10")


def test_oauth_credential_has_independent_extra_values() -> None:
    first = OAuthCredential(access="access", refresh="refresh", expires=1)
    second = OAuthCredential(access="access", refresh="refresh", expires=1)

    first.extra["account_id"] = "account"

    assert second.extra == {}
