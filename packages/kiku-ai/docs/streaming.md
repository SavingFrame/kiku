# Streaming contract

## Direct async iteration

Kiku providers and API adapters return an `AsyncIterator[AssistantMessageEvent]` directly:

```python
stream = provider.stream(model, context)

async for event in stream:
    render(event)
```

The provider method itself is synchronous. HTTP work starts when the caller begins iterating over the returned async generator. This gives normal async-generator backpressure and avoids a background producer task or event queue.

## Final result

The terminal event carries the complete assistant message:

```python
message = None
async for event in provider.stream(model, context):
    render(event)
    if event.type == "done":
        message = event.message
    elif event.type == "error":
        message = event.error
```

Consumers that need the final message must retain it from `DoneEvent` or `ErrorEvent`. There is no independent `stream.result()` operation. Stopping iteration early means no final result is produced.

## Event protocol

The event protocol is:

```text
start
text_start
text_delta
text_end
thinking_start
thinking_delta
thinking_end
tool_call_start
tool_call_delta
tool_call_end
done
error
```

Incremental events include the latest partial `AssistantMessage`. Its `stop_reason` is `None` until a terminal event.

A typical text stream is:

```text
start                     content = []
text_start                content = [TextContent("")]
text_delta("Hello")       content = [TextContent("Hello")]
text_delta(" world")      content = [TextContent("Hello world")]
text_end                  content = [TextContent("Hello world")]
done                      final AssistantMessage
```

## Tool-call streaming

Tool arguments arrive as JSON fragments. During `tool_call_delta`, arguments are only a best-effort parse. Consumers must treat them defensively. Final parsed arguments are available in `tool_call_end`.

## Errors and cancellation

Request and provider failures are converted to `ErrorEvent` where possible. The event contains the partial response and a concrete `error` stop reason.

Cancellation uses normal asyncio task cancellation. Cancelling the task consuming the async iterator propagates `CancelledError` through the adapter and closes active `httpx` response contexts. Cancellation is not converted into a terminal event because the consumer task no longer exists to receive it.

## Pi and Tau design sources

The event shapes follow Pi, while direct async-generator ownership follows Tau's Python implementation:

- Pi: `packages/ai/src/types.ts`
- Tau: `src/tau_agent/provider.py`
- Tau: `src/tau_ai/openai_codex.py`
- Tau: `src/tau_ai/stream.py`
