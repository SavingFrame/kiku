from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from kiku_ai.auth import ModelAuth
from kiku_ai.context import Context
from kiku_ai.events import AssistantMessageEvent, DoneEvent, ErrorEvent, StartEvent, TextDeltaEvent
from kiku_ai.messages import AssistantMessage, StopReason, TextContent, Usage
from kiku_ai.models import Model
from kiku_ai.streaming import StreamOptions


@dataclass
class FakeProviderState:
    call_count: int = 0


type FakeResponseFactory = Callable[
    [Context, StreamOptions | None, FakeProviderState, Model],
    AssistantMessage | Awaitable[AssistantMessage],
]
type FakeResponseStep = AssistantMessage | FakeResponseFactory


class FakeApiAdapter:
    def __init__(self, responses: Sequence[FakeResponseStep] | None = None) -> None:
        self.responses = list(responses or [])
        self.state = FakeProviderState()

    def enqueue(self, response: FakeResponseStep) -> None:
        self.responses.append(response)

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
        *,
        auth: ModelAuth,
        base_url: str,
    ) -> AsyncIterator[AssistantMessageEvent]:
        del auth, base_url
        step = self.responses.pop(0) if self.responses else None
        self.state.call_count += 1

        async def iterator() -> AsyncIterator[AssistantMessageEvent]:
            try:
                if step is None:
                    raise RuntimeError("No fake response is queued")

                if isinstance(step, AssistantMessage):
                    response = step
                else:
                    resolved = step(context, options, self.state, model)
                    response = resolved if isinstance(resolved, AssistantMessage) else await resolved

                for event in self._response_events(response):
                    yield event
            except Exception as error:
                message = AssistantMessage(
                    timestamp=datetime.now(UTC),
                    content=[],
                    usage=Usage(),
                    stop_reason=StopReason.ERROR,
                    error_message=str(error),
                )
                yield ErrorEvent(reason=StopReason.ERROR, error=message)

        return iterator()

    def _response_events(self, response: AssistantMessage) -> Iterator[AssistantMessageEvent]:
        if response.stop_reason is None:
            raise ValueError("Fake response requires a terminal stop reason")

        partial = response.model_copy(update={"content": [], "usage": Usage(), "stop_reason": None})
        yield StartEvent(partial=partial)

        partial_content: list[TextContent] = []
        for content_index, content in enumerate(response.content):
            if not isinstance(content, TextContent):
                error = response.model_copy(
                    update={
                        "content": partial_content,
                        "stop_reason": StopReason.ERROR,
                        "error_message": "FakeApiAdapter currently supports text responses only",
                    }
                )
                yield ErrorEvent(reason=StopReason.ERROR, error=error)
                return

            partial_content.append(TextContent(content=""))
            accumulated = ""
            for delta in _text_chunks(content.content):
                accumulated += delta
                partial_content[content_index] = TextContent(content=accumulated)
                partial = response.model_copy(
                    update={"content": list(partial_content), "usage": Usage(), "stop_reason": None}
                )
                yield TextDeltaEvent(
                    content_index=content_index,
                    delta=delta,
                    partial=partial,
                )

        if response.stop_reason == StopReason.ERROR:
            yield ErrorEvent(reason=StopReason.ERROR, error=response)
        elif response.stop_reason == StopReason.ABORTED:
            yield ErrorEvent(reason=StopReason.ABORTED, error=response)
        elif response.stop_reason == StopReason.LENGTH:
            yield DoneEvent(reason=StopReason.LENGTH, message=response)
        elif response.stop_reason == StopReason.TOOL_USE:
            yield DoneEvent(reason=StopReason.TOOL_USE, message=response)
        else:
            yield DoneEvent(reason=StopReason.STOP, message=response)


def _text_chunks(text: str, chunk_size: int = 8) -> list[str]:
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]
