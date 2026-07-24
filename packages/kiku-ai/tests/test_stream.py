import asyncio
from datetime import UTC, datetime

from kiku_ai import (
    AssistantMessage,
    AssistantMessageStream,
    DoneEvent,
    ErrorEvent,
    StartEvent,
    StopReason,
    TextContent,
    TextDeltaEvent,
    Usage,
)


def make_message(
    content: str,
    stop_reason: StopReason = StopReason.STOP,
    error_message: str | None = None,
) -> AssistantMessage:
    return AssistantMessage(
        timestamp=datetime.now(UTC),
        content=[TextContent(content=content)],
        usage=Usage(),
        stop_reason=stop_reason,
        error_message=error_message,
    )


async def test_iterates_events_in_order() -> None:
    stream = AssistantMessageStream()
    partial = make_message("Hello")
    final = make_message("Hello world")
    events = [
        StartEvent(partial=partial),
        TextDeltaEvent(content_index=0, delta=" world", partial=final),
        DoneEvent(reason=StopReason.STOP, message=final),
    ]

    for event in events:
        stream.push(event)

    received = [event async for event in stream]

    assert received == events


async def test_streams_incremental_text_with_updated_partials() -> None:
    stream = AssistantMessageStream()
    empty = AssistantMessage(
        timestamp=datetime.now(UTC),
        content=[],
        usage=Usage(),
        stop_reason=StopReason.STOP,
    )
    chunks = ["Hello", " world", "!"]
    partial_texts = ["Hello", "Hello world", "Hello world!"]
    final = make_message(partial_texts[-1])

    stream.push(StartEvent(partial=empty))
    for chunk, partial_text in zip(chunks, partial_texts, strict=True):
        stream.push(
            TextDeltaEvent(
                content_index=0,
                delta=chunk,
                partial=make_message(partial_text),
            )
        )
    stream.push(DoneEvent(reason=StopReason.STOP, message=final))

    events = [event async for event in stream]
    deltas = [event for event in events if isinstance(event, TextDeltaEvent)]

    assert "".join(event.delta for event in deltas) == "Hello world!"
    for event, expected_text in zip(deltas, partial_texts, strict=True):
        content = event.partial.content[0]
        assert isinstance(content, TextContent)
        assert content.content == expected_text
    assert await stream.result() is final


async def test_result_waits_for_terminal_event() -> None:
    stream = AssistantMessageStream()
    final = make_message("Complete")
    result_task = asyncio.create_task(stream.result())

    assert not result_task.done()

    stream.push(DoneEvent(reason=StopReason.STOP, message=final))

    assert await result_task is final


async def test_result_is_available_after_iteration() -> None:
    stream = AssistantMessageStream()
    final = make_message("Complete")
    stream.push(DoneEvent(reason=StopReason.STOP, message=final))

    received = [event async for event in stream]

    assert len(received) == 1
    assert await stream.result() is final


async def test_result_returns_error_message() -> None:
    stream = AssistantMessageStream()
    error = make_message("Partial", StopReason.ERROR, "Provider failed")
    stream.push(ErrorEvent(reason=StopReason.ERROR, error=error))

    assert await stream.result() is error


async def test_multiple_result_calls_return_same_message() -> None:
    stream = AssistantMessageStream()
    final = make_message("Complete")
    stream.push(DoneEvent(reason=StopReason.STOP, message=final))

    first, second = await asyncio.gather(stream.result(), stream.result())

    assert first is final
    assert second is final


async def test_push_ignores_events_after_termination() -> None:
    stream = AssistantMessageStream()
    final = make_message("Complete")
    stream.push(DoneEvent(reason=StopReason.STOP, message=final))
    stream.push(StartEvent(partial=make_message("Too late")))

    received = [event async for event in stream]

    assert len(received) == 1
    assert received[0].type == "done"
    assert stream.queue.empty()
