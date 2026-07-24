# Streaming contract

## Why Kiku needs a stream object

A bare Python `AsyncIterator` can deliver incremental events, but it does not provide a convenient independent final-result contract. Kiku should expose an object that supports both event iteration and final-message retrieval:

```python
class AssistantMessageStream:
    def __aiter__(self) -> AsyncIterator[AssistantMessageEvent]: ...

    async def result(self) -> AssistantMessage: ...
```

Usage:

```python
provider = provider_manager.get_provider(model.provider)
stream = provider.stream(model, context)

async for event in stream:
    render(event)

message = await stream.result()
```

Pi uses this contract in `packages/ai/src/utils/event-stream.ts`.

## Event protocol

The full target protocol is:

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

The initial implementation only needs:

```text
start
text_delta
done
error
```

More event types can be added without changing the basic stream abstraction.

## Partial assistant message

Incremental events should include the latest partial `AssistantMessage`. Consumers can either process the delta or replace their displayed partial message.

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

Tool arguments arrive as JSON fragments. During `tool_call_delta`, the arguments are only a best-effort parse:

```text
{"path":"README
{"path":"README.md","line
{"path":"README.md","line":10}
```

Consumers must treat partial arguments defensively. The final parsed arguments are available at `tool_call_end`.

This enables a UI to display a target path before the complete tool call has arrived.

## Terminal events

A successful stream terminates with `DoneEvent` carrying an assistant message whose stop reason is one of:

```text
stop
tool_use
length
```

A failed stream terminates with `ErrorEvent` carrying an assistant message whose stop reason is:

```text
error
aborted
```

Request, model, authentication, and runtime failures should normally be encoded in the stream instead of escaping as exceptions after a stream has been returned.

Programming errors before a stream can be constructed may still raise directly.

## Result semantics

`result()` should resolve to the same terminal assistant message carried by `done` or `error`.

Required behavior:

- Multiple calls to `result()` return the same message
- `result()` may be awaited before or after event iteration
- The stream cannot accept events after a terminal event
- Cancellation returns a partial assistant message with `stop_reason="aborted"`
- Provider errors preserve any content and usage already received

## Fake provider behavior

The fake provider should translate a scripted final message into realistic events. It should not bypass the event contract.

For a scripted text response, it can split text into deterministic chunks and emit:

```text
start
text_start
text_delta...
text_end
done
```

For a scripted tool call, it should emit partial JSON argument chunks and a final tool-call event.

## Pi design source

- `packages/ai/src/types.ts`, type `AssistantMessageEvent`
- `packages/ai/src/utils/event-stream.ts`
- `packages/ai/src/providers/faux.ts`
- `packages/ai/src/api/anthropic-messages.ts`, function `stream`
