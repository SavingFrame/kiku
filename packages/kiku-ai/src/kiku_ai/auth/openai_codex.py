import os
from collections.abc import Mapping

from kiku_ai.auth.base import ModelAuth
from kiku_ai.auth.credentials import Credential

OPENAI_CODEX_ACCESS_TOKEN = "OPENAI_CODEX_ACCESS_TOKEN"
OPENAI_CODEX_ACCOUNT_ID = "OPENAI_CODEX_ACCOUNT_ID"


class OpenAICodexAuthError(ValueError):
    pass


class OpenAICodexEnvAuth:
    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env = env

    async def resolve(
        self,
        credential: Credential | None,
    ) -> ModelAuth | None:
        del credential
        values = os.environ if self._env is None else self._env
        access_token = values.get(OPENAI_CODEX_ACCESS_TOKEN, "").strip()
        account_id = values.get(OPENAI_CODEX_ACCOUNT_ID, "").strip()

        if not access_token and not account_id:
            return None
        if not access_token:
            raise OpenAICodexAuthError(
                f"{OPENAI_CODEX_ACCESS_TOKEN} is required when {OPENAI_CODEX_ACCOUNT_ID} is set"
            )
        if not account_id:
            raise OpenAICodexAuthError(
                f"{OPENAI_CODEX_ACCOUNT_ID} is required when {OPENAI_CODEX_ACCESS_TOKEN} is set"
            )

        return ModelAuth(
            api_key=access_token,
            headers={"chatgpt-account-id": account_id},
        )
