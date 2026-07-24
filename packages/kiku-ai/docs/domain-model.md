# Domain model

## Context

`Context` is the complete provider-neutral input needed to generate the next assistant message.

Conceptually:

```python
class Context(BaseModel):
    system_prompt: str | None = None
    messages: list[Message]
    tools: list[Tool] | None = None
```

It contains:

- An optional system prompt
- Ordered conversation history
- Optional tool declarations visible to the model

It should not contain:

- The selected model
- Authentication credentials
- Timeout or retry settings
- Provider-specific request options
- Executable Python tool callbacks
- UI state

The selected `Model`, `Context`, and `StreamOptions` are separate arguments to a stream request:

```python
stream = models.stream(model, context, options)
```

This separation allows the same context to be sent to another model or provider.

Pi source: `packages/ai/src/types.ts`, interface `Context`.

## Message

`Message` is a discriminated union with three model-visible roles:

```text
Message
├── UserMessage
├── AssistantMessage
└── ToolResultMessage
```

Every message has a timestamp. Assistant and tool-result messages carry additional metadata.

### UserMessage

A user message contains either a plain string or a sequence of text and image blocks.

Target shape:

```python
class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str | list[TextContent | ImageContent]
    timestamp: datetime
```

### AssistantMessage

An assistant message is the final normalized result of one model request.

```python
class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: list[TextContent | ThinkingContent | ToolCall]
    api: str
    provider: str
    model: str
    usage: Usage
    stop_reason: StopReason
    error_message: str | None = None
    response_id: str | None = None
    timestamp: datetime
```

The `api`, `provider`, and `model` fields preserve provenance. They are also useful when replaying a conversation through a different provider.

### ToolResultMessage

A tool result links back to a specific tool call:

```python
class ToolResultMessage(BaseModel):
    role: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    tool_name: str
    content: list[TextContent | ImageContent]
    is_error: bool
    timestamp: datetime
```

It contains data returned by a tool. It does not contain the executable callback.

## Content blocks

### TextContent

```python
class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str
```

### ThinkingContent

```python
class ThinkingContent(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    thinking_signature: str | None = None
    redacted: bool = False
```

Provider signatures are needed by some APIs for multi-turn reasoning continuity. They may be invalid when switching to another model.

### ImageContent

```python
class ImageContent(BaseModel):
    type: Literal["image"] = "image"
    data: str
    mime_type: str
```

`data` is base64-encoded image data.

### ToolCall

```python
class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any]
```

During streaming, `arguments` may be a best-effort parse of incomplete JSON. Final arguments are available when the tool-call end event arrives.

## Tool

A `Tool` is a declaration sent to the model:

```python
class Tool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
```

`parameters` is a JSON Schema object.

The executable tool interface belongs in `kiku-agent`, for example:

```python
class AgentTool(Tool):
    async def execute(...) -> AgentToolResult: ...
```

Keeping execution out of `kiku-ai` allows the AI package to be used without an agent runtime.

## Model

A model is serializable metadata, not a client object:

```python
class Model(BaseModel):
    id: str
    name: str
    provider: str
    api: str
    base_url: str
    reasoning: bool = False
    input: list[Literal["text", "image"]]
    context_window: int
    max_output_tokens: int
    cost: ModelCost
```

The current Kiku `Model` uses `context_model`. The target name should be `context_window` because it describes a token limit, not another model.

`provider` identifies the runtime owner, such as `openai-codex`. `api` identifies the wire protocol, such as `openai-codex-responses`.

## Usage

Normalized usage should include:

```python
class Usage(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int | None = None
    total_tokens: int = 0
    cost: Cost
```

Reasoning tokens are normally a subset of output tokens when reported by a provider.

## StopReason

The normalized values are:

```text
stop       normal completion
tool_use   model requested tool execution
length     output limit reached
error      request or provider failure
aborted    caller cancelled the request
```

Failures should still produce an `AssistantMessage`. Partial content and partial usage can therefore be retained.

## Cross-provider replay

Before sending history to a provider, an API adapter may need to:

- Replace unsupported images with placeholders
- Remove provider-specific reasoning signatures
- Convert foreign thinking blocks to ordinary text
- Normalize tool-call IDs
- Supply missing tool results for orphaned calls
- Exclude aborted or errored assistant turns from replay

Pi implements shared preprocessing in `packages/ai/src/api/transform-messages.ts` and protocol-specific conversion in each API adapter.
