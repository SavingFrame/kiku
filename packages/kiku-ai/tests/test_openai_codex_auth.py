import pytest

from kiku_ai.auth import ModelAuth, OpenAICodexAuthError, OpenAICodexEnvAuth


async def test_resolves_codex_auth_from_environment() -> None:
    auth = OpenAICodexEnvAuth(
        {
            "OPENAI_CODEX_ACCESS_TOKEN": "access-token",
            "OPENAI_CODEX_ACCOUNT_ID": "account-id",
        }
    )

    assert await auth.resolve(None) == ModelAuth(
        api_key="access-token",
        headers={"chatgpt-account-id": "account-id"},
    )


async def test_resolves_codex_auth_from_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_CODEX_ACCESS_TOKEN", "access-token")
    monkeypatch.setenv("OPENAI_CODEX_ACCOUNT_ID", "account-id")

    assert await OpenAICodexEnvAuth().resolve(None) == ModelAuth(
        api_key="access-token",
        headers={"chatgpt-account-id": "account-id"},
    )


async def test_returns_none_when_codex_environment_is_not_configured() -> None:
    assert await OpenAICodexEnvAuth({}).resolve(None) is None


@pytest.mark.parametrize(
    ("env", "missing_name"),
    [
        ({"OPENAI_CODEX_ACCOUNT_ID": "account-id"}, "OPENAI_CODEX_ACCESS_TOKEN"),
        ({"OPENAI_CODEX_ACCESS_TOKEN": "access-token"}, "OPENAI_CODEX_ACCOUNT_ID"),
    ],
)
async def test_rejects_partial_codex_environment(
    env: dict[str, str],
    missing_name: str,
) -> None:
    with pytest.raises(OpenAICodexAuthError, match=missing_name):
        await OpenAICodexEnvAuth(env).resolve(None)


async def test_treats_blank_codex_environment_values_as_missing() -> None:
    auth = OpenAICodexEnvAuth(
        {
            "OPENAI_CODEX_ACCESS_TOKEN": " ",
            "OPENAI_CODEX_ACCOUNT_ID": "\t",
        }
    )

    assert await auth.resolve(None) is None
