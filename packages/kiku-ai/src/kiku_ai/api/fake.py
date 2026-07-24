import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from kiku_ai.auth import ModelAuth
from kiku_ai.context import Context
from kiku_ai.events import (
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    StartEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from kiku_ai.messages import AssistantMessage, StopReason, TextContent, ThinkingContent, ToolCall, Usage
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

        partial_content: list[TextContent | ThinkingContent | ToolCall] = []
        for content_index, content in enumerate(response.content):
            if isinstance(content, TextContent):
                partial_content.append(TextContent(content=""))
                yield TextStartEvent(
                    content_index=content_index,
                    partial=_partial(response, partial_content),
                )
                accumulated = ""
                for delta in _chunks(content.content):
                    accumulated += delta
                    partial_content[content_index] = TextContent(content=accumulated)
                    yield TextDeltaEvent(
                        content_index=content_index,
                        delta=delta,
                        partial=_partial(response, partial_content),
                    )
                yield TextEndEvent(
                    content_index=content_index,
                    content=content.content,
                    partial=_partial(response, partial_content),
                )
            elif isinstance(content, ThinkingContent):
                partial_content.append(content.model_copy(update={"thinking": ""}))
                yield ThinkingStartEvent(
                    content_index=content_index,
                    partial=_partial(response, partial_content),
                )
                accumulated = ""
                for delta in _chunks(content.thinking):
                    accumulated += delta
                    partial_content[content_index] = content.model_copy(update={"thinking": accumulated})
                    yield ThinkingDeltaEvent(
                        content_index=content_index,
                        delta=delta,
                        partial=_partial(response, partial_content),
                    )
                yield ThinkingEndEvent(
                    content_index=content_index,
                    content=content.thinking,
                    partial=_partial(response, partial_content),
                )
            else:
                arguments_json = json.dumps(content.arguments, separators=(",", ":"))
                partial_content.append(content.model_copy(update={"arguments": {}}))
                yield ToolCallStartEvent(
                    content_index=content_index,
                    partial=_partial(response, partial_content),
                )
                accumulated = ""
                for delta in _chunks(arguments_json):
                    accumulated += delta
                    partial_content[content_index] = content.model_copy(
                        update={"arguments": _try_parse_arguments(accumulated)}
                    )
                    yield ToolCallDeltaEvent(
                        content_index=content_index,
                        delta=delta,
                        partial=_partial(response, partial_content),
                    )
                partial_content[content_index] = content.model_copy(deep=True)
                yield ToolCallEndEvent(
                    content_index=content_index,
                    tool_call=content.model_copy(deep=True),
                    partial=_partial(response, partial_content),
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


def _partial(
    response: AssistantMessage,
    content: list[TextContent | ThinkingContent | ToolCall],
) -> AssistantMessage:
    return response.model_copy(update={"content": list(content), "usage": Usage(), "stop_reason": None})


def _try_parse_arguments(arguments: str) -> dict[str, object]:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _chunks(value: str, chunk_size: int = 8) -> list[str]:
    return [value[index : index + chunk_size] for index in range(0, len(value), chunk_size)]
