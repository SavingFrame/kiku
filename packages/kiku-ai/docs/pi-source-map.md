# Pi source map

The design documentation was derived from Pi at commit:

```text
65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a
```

Repository tree:

<https://github.com/earendil-works/pi/tree/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a>

## Package overview

- [AI README](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/README.md)
- [Agent README](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/agent/README.md)
- [TUI README](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/tui/README.md)
- [AI package metadata](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/package.json)
- [Agent package metadata](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/agent/package.json)
- [TUI package metadata](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/tui/package.json)

## Canonical models

- [`packages/ai/src/types.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/types.ts)

Contains:

- `Context`
- Message unions
- Content blocks
- Tool declarations
- `Model`
- `Usage`
- Stop reasons
- Streaming events
- Stream option types

## Provider registry and dispatch

- [`packages/ai/src/models.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/models.ts)

Contains:

- `Provider`
- `Models`
- `createModels()`
- `createProvider()`
- Authentication application
- Provider routing
- `stream()` and `complete()`
- Cost calculation

## Streaming

- [`packages/ai/src/utils/event-stream.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/utils/event-stream.ts)
- [`packages/ai/src/api/lazy.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/api/lazy.ts)

These files provide the async event stream, final result, lazy setup, and setup-error conversion.

## Message compatibility

- [`packages/ai/src/api/transform-messages.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/api/transform-messages.ts)

Contains cross-provider replay transformations, unsupported image handling, tool-call ID normalization, and orphaned tool-result repair.

## Example provider and protocol adapter

- [`packages/ai/src/providers/anthropic.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/providers/anthropic.ts)
- [`packages/ai/src/api/anthropic-messages.lazy.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/api/anthropic-messages.lazy.ts)
- [`packages/ai/src/api/anthropic-messages.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/api/anthropic-messages.ts)
- [`packages/ai/src/api/simple-options.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/api/simple-options.ts)

These demonstrate the separation between provider metadata/authentication and protocol-specific payload/stream logic.

## Upstream scripted provider

- [`packages/ai/src/providers/faux.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/providers/faux.ts)

This is the source for the planned scripted Kiku test provider.

## OpenAI Codex

- [`packages/ai/src/providers/openai-codex.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/providers/openai-codex.ts)
- [`packages/ai/src/providers/openai-codex.models.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/providers/openai-codex.models.ts)
- [`packages/ai/src/api/openai-codex-responses.lazy.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/api/openai-codex-responses.lazy.ts)
- [`packages/ai/src/api/openai-codex-responses.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/api/openai-codex-responses.ts)
- [`packages/ai/src/auth/oauth/openai-codex.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/ai/src/auth/oauth/openai-codex.ts)

These provide the Codex provider definition, Responses transport, headers, token refresh, browser/device login, and account-ID extraction.

## Agent boundary

- [`packages/agent/src/types.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/agent/src/types.ts)
- [`packages/agent/src/agent-loop.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/agent/src/agent-loop.ts)
- [`packages/agent/src/agent.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/agent/src/agent.ts)

These show that tool execution, state, queues, and automatic continuation belong above the AI package.

## TUI boundary

- [`packages/tui/src/tui.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/tui/src/tui.ts)
- [`packages/tui/src/terminal.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/tui/src/terminal.ts)
- [`packages/tui/src/index.ts`](https://github.com/earendil-works/pi/blob/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a/packages/tui/src/index.ts)

These show that Pi's TUI is a generic terminal framework rather than an agent runtime.
