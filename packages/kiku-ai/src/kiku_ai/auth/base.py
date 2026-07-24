from dataclasses import dataclass, field
from typing import Protocol

from kiku_ai.auth.credentials import Credential


@dataclass(frozen=True)
class ModelAuth:
    api_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class ProviderAuth(Protocol):
    async def resolve(
        self,
        credential: Credential | None,
    ) -> ModelAuth | None: ...


class KeylessAuth:
    async def resolve(
        self,
        credential: Credential | None,
    ) -> ModelAuth:
        del credential
        return ModelAuth()
