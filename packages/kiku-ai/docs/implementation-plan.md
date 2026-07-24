# Incremental implementation plan

Each milestone must leave the package runnable and tested. Do not begin real Codex OAuth until the provider-neutral contracts work with a fake provider.

## Milestone 0: package layout

Target:

```text
packages/kiku-ai/
├── pyproject.toml
├── src/kiku_ai/
│   ├── __init__.py
│   ├── types.py
│   ├── events.py
│   ├── stream.py
│   ├── models.py
│   ├── provider_manager.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py
│       └── fake.py
└── tests/
```

Reason:

- The distribution is named `kiku-ai`
- The Python import package should be `kiku_ai`
- A top-level `src/types.py` risks conflicting with the standard-library `types` module

Completion test:

```python
import kiku_ai
```

## Milestone 1: minimum canonical models

Implement:

- `TextContent`
- `UserMessage`
- `AssistantMessage`
- `Message`
- `Usage`
- `StopReason`
- `Tool`
- `ToolCall`
- `ToolResultMessage`
- `Context`
- `Model`
- `StreamOptions`

Use Pydantic discriminated unions where messages or content blocks are serialized.

Tests:

- Construct every model
- Serialize to JSON
- Deserialize from JSON
- Reject invalid discriminators
- Preserve tool-call arguments

## Milestone 2: event stream

Implement:

- `StartEvent`
- `TextDeltaEvent`
- `DoneEvent`
- `ErrorEvent`
- `AssistantMessageStream`

Tests:

- Iterate events in order
- Await `result()` before iteration completes
- Await `result()` after iteration
- Return the terminal message from both done and error
- Ignore or reject pushes after termination

## Milestone 3: fake provider

Implement a scripted provider with:

```python
fake = FakeProvider(responses=[...])
fake.enqueue(response)
fake.get_model(model_id)
fake.stream(model, context, options)
```

The constructor and `enqueue()` method are test controls specific to `FakeProvider`. Streaming remains part of the shared `Provider` interface.

Tests:

- Text response
- Multiple sequential responses
- Empty response queue
- Error response
- Aborted response
- Deterministic event ordering

Then add thinking and tool-call event support.

## Milestone 4: provider manager

Implement `ProviderManager` with:

- `register()`
- `unregister()`
- `get_provider()`
- `get_models()`
- `get_model()`

Tests:

- Register and retrieve a provider
- Return no provider for an unknown ID
- Aggregate models from registered providers
- Look up a model by provider and model ID
- Replace a provider with the same ID
- Remove a provider and its models

Keep streaming on `Provider`. Add authentication resolution and dynamic catalog refresh to `ProviderManager` in the later milestones that introduce those features.

## Milestone 5: Codex request serialization

Implement a pure OpenAI Codex Responses request builder.

Tests should verify:

- System prompt conversion
- User text conversion
- Assistant replay
- Tool declaration conversion
- Tool-call replay
- Tool-result replay
- Reasoning option conversion
- Maximum output token option

No network access is needed.

## Milestone 6: Codex SSE parser

Implement provider-event to Kiku-event conversion using stored SSE fixtures.

Tests should verify:

- Text deltas
- Reasoning deltas
- Partial tool JSON
- Final tool arguments
- Usage
- Stop reasons
- Error events
- Cancellation

## Milestone 7: real HTTP with injected credentials

Add `httpx` and an `OpenAICodexProvider` that accepts explicit credentials.

Use mocked HTTP tests before a live smoke test. Keep live tests opt-in and ensure they never print tokens.

## Milestone 8: OAuth and credential store

Implement persistent credentials, login, refresh, and logout only after the HTTP path works.

## Milestone 9: agent package

After fake tool calls work, create `kiku-agent` and implement the smallest loop:

```text
prompt
model response
execute tool calls
append tool results
model continuation
stop
```

Use the fake provider for all agent-loop tests.

## Milestone 10: TUI package

Stabilize AI and agent events before binding them to terminal components.

## First recommended coding task

Implement Milestones 0 through 2 only. This produces the foundational types and stream contract while keeping the change small enough to review carefully.
