import asyncio
from datetime import UTC, datetime

from kiku_ai import Context, DoneEvent, ErrorEvent, TextDeltaEvent, UserMessage
from kiku_ai.auth import MemoryCredentialStore
from kiku_ai.providers import OpenAICodexProvider


async def main() -> None:
    provider = OpenAICodexProvider(
        credential_store=MemoryCredentialStore(),
    )

    model = provider.get_model("gpt-5.4-mini")
    assert model is not None

    context = Context(
        messages=[
            UserMessage(
                timestamp=datetime.now(UTC),
                content="Reply with exactly: Codex connection works",
            )
        ]
    )

    async for event in provider.stream(model, context):
        if isinstance(event, TextDeltaEvent):
            print(event.delta, end="", flush=True)
        elif isinstance(event, DoneEvent):
            print(f"\nDone: {event.reason}")
            print(event.message)
            print(event.model_extra)
        elif isinstance(event, ErrorEvent):
            print(f"\nError: {event.error.error_message}")


if __name__ == "__main__":
    asyncio.run(main())
