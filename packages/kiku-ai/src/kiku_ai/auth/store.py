import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from kiku_ai.auth.credentials import Credential

CredentialUpdate = Callable[[Credential | None], Awaitable[Credential | None]]


class CredentialStore(Protocol):
    async def read(self, provider_id: str) -> Credential | None: ...

    async def modify(
        self,
        provider_id: str,
        update: CredentialUpdate,
    ) -> Credential | None: ...

    async def delete(self, provider_id: str) -> None: ...


class MemoryCredentialStore:
    def __init__(self) -> None:
        self._credentials: dict[str, Credential] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def read(self, provider_id: str) -> Credential | None:
        return self._credentials.get(provider_id)

    async def modify(
        self,
        provider_id: str,
        update: CredentialUpdate,
    ) -> Credential | None:
        async with self._lock_for(provider_id):
            current = self._credentials.get(provider_id)
            credential = await update(current)
            if credential is not None:
                self._credentials[provider_id] = credential
                return credential
            return current

    async def delete(self, provider_id: str) -> None:
        async with self._lock_for(provider_id):
            self._credentials.pop(provider_id, None)

    def _lock_for(self, provider_id: str) -> asyncio.Lock:
        return self._locks.setdefault(provider_id, asyncio.Lock())
