import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from events import (
    AssistantMessage,
    Context,
    DoneEvent,
    ErrorEvent,
    StartEvent,
    StopReason,
    TextContent,
    TextDeltaEvent,
    Usage,
)
from models import Model
from provider import Provider
from stream import AssistantMessageStream, StreamOptions


@dataclass
class FakeProviderState:
    call_count: int = 0


type FakeResponseFactory = Callable[
    [Context, StreamOptions | None, FakeProviderState, Model],
    AssistantMessage | Awaitable[AssistantMessage],
]
type FakeResponseStep = AssistantMessage | FakeResponseFactory


class FakeProvider(Provider):
    id = "fake"
    name = "Fake"

    def __init__(
        self,
        responses: Sequence[FakeResponseStep] | None = None,
        models: Sequence[Model] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.models = list(models or [_default_model()])
        self.state = FakeProviderState()
        self._tasks: set[asyncio.Task[None]] = set()

    def enqueue(self, response: FakeResponseStep) -> None:
        self.responses.append(response)

    def get_models(self) -> Sequence[Model]:
        return self.models

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantMessageStream:
        stream = AssistantMessageStream()
        step = self.responses.pop(0) if self.responses else None
        self.state.call_count += 1
        task = asyncio.create_task(self._produce(stream, step, model, context, options))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return stream

    async def _produce(
        self,
        stream: AssistantMessageStream,
        step: FakeResponseStep | None,
        model: Model,
        context: Context,
        options: StreamOptions | None,
    ) -> None:
        try:
            if step is None:
                raise RuntimeError("No fake response is queued")

            if isinstance(step, AssistantMessage):
                response = step
            else:
                resolved = step(context, options, self.state, model)
                if isinstance(resolved, AssistantMessage):
                    response = resolved
                else:
                    response = await resolved
            self._stream_response(stream, response)
        except Exception as error:
            message = AssistantMessage(
                timestamp=datetime.now(UTC),
                content=[],
                usage=Usage(),
                stop_reason=StopReason.ERROR,
                error_message=str(error),
            )
            stream.push(ErrorEvent(reason=StopReason.ERROR, error=message))

    def _stream_response(
        self,
        stream: AssistantMessageStream,
        response: AssistantMessage,
    ) -> None:
        partial = response.model_copy(update={"content": [], "usage": Usage()})
        stream.push(StartEvent(partial=partial))

        partial_content: list[TextContent] = []
        for content_index, content in enumerate(response.content):
            if not isinstance(content, TextContent):
                error = response.model_copy(
                    update={
                        "content": partial_content,
                        "stop_reason": StopReason.ERROR,
                        "error_message": "FakeProvider currently supports text responses only",
                    }
                )
                stream.push(ErrorEvent(reason=StopReason.ERROR, error=error))
                return

            partial_content.append(TextContent(content=""))
            accumulated = ""
            for delta in _text_chunks(content.content):
                accumulated += delta
                partial_content[content_index] = TextContent(content=accumulated)
                partial = response.model_copy(
                    update={"content": list(partial_content), "usage": Usage()}
                )
                stream.push(
                    TextDeltaEvent(
                        content_index=content_index,
                        delta=delta,
                        partial=partial,
                    )
                )

        if response.stop_reason in (StopReason.ERROR, StopReason.ABORTED):
            stream.push(ErrorEvent(reason=response.stop_reason, error=response))
        else:
            stream.push(DoneEvent(reason=response.stop_reason, message=response))


def _default_model() -> Model:
    return Model(
        id="fake-model",
        name="Fake Model",
        provider="fake",
        api="fake",
        context_model=128_000,
        max_output_tokens=16_384,
    )


def _text_chunks(text: str, chunk_size: int = 8) -> list[str]:
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]
