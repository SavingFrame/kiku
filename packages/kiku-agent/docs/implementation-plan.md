# kiku-agent implementation plan

## Goal

Build the smallest agent runtime needed by Kiku while preserving the boundaries that let it grow into a reusable coding-agent harness.

The package keeps Pi's three responsibilities without copying its TypeScript API one to one:

```text
Agent ────────────┐
                  ├── run_agent_loop ──→ kiku-ai
AgentHarness ─────┘
```

`run_agent_loop` is the shared stateless execution algorithm. `Agent` is the lightweight in-memory API. `AgentHarness` is the session-backed coding-agent API. They are sibling orchestration layers and neither depends on the other.

## Design rules

- Keep models, messages, `Context`, tool declarations, provider lookup, and provider streaming in `kiku-ai`.
- Reuse `kiku-ai` contracts directly instead of introducing agent-prefixed copies.
- Keep executable tools, tool execution, and model continuation in `kiku-agent`.
- Separate transient `Agent` state from durable harness state.
- Use protocols only at side-effect boundaries that need interchangeable implementations, such as session storage, filesystem access, and process execution.
- Use an async generator for the low-level loop. Async iteration provides event delivery, backpressure, and cancellation without an event-sink abstraction.
- Let `ProviderManager` dispatch model requests. Do not add a second stream-function abstraction before a concrete need appears.
- Pass the initial loop inputs directly. Do not introduce an agent-loop configuration object until the argument surface requires one.
- Snapshot agent configuration when a run starts. Changes must not mutate an in-flight provider request. Add finer save-point refresh only when active-run configuration changes are required.
- Preserve deterministic event, message, and tool-result ordering.
- Add narrow hooks for concrete needs instead of building a generic extension framework early.
- Do not require sessions, coding tools, or the harness to use the lightweight `Agent`.
- Every milestone must leave the workspace importable and tested.

## Target package layout

The layout should grow incrementally toward:

```text
packages/kiku-agent/
├── pyproject.toml
├── src/kiku_agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── events.py
│   ├── loop.py
│   ├── tools.py
│   ├── harness.py
│   ├── sessions/
│   │   ├── base.py
│   │   ├── memory.py
│   │   └── jsonl.py
│   ├── execution/
│   │   ├── base.py
│   │   └── local.py
│   └── standard_tools/
│       ├── read.py
│       ├── write.py
│       ├── edit.py
│       └── shell.py
└── tests/
```

Files and directories should only be added when their milestone starts.

## Milestone 1: runtime contracts

Implement only the contracts that do not already exist in `kiku-ai`:

- `AgentTool`
- `AgentToolResult`
- `AgentEvent`

Use existing `kiku-ai` types directly:

- `Message` instead of `AgentMessage`
- `Context` instead of `AgentContext`
- `Model`
- `StreamOptions`
- `ProviderManager`

Do not introduce `AgentLoopConfig`, `StreamFunction`, or `AgentEventSink`. Define `AgentState` with the stateful `Agent` in Milestone 3.

### Executable tools

`AgentTool` extends the model-visible `kiku_ai.Tool` model and adds an abstract async executor:

```python
class AgentTool(Tool, ABC):
    @abstractmethod
    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> AgentToolResult:
        ...
```

A concrete tool is both the declaration sent to a provider and the executable runtime object:

```python
class ReadTool(AgentTool):
    name: str = "read"
    description: str = "Read a file"
    parameters: dict[str, Any] = {...}

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> AgentToolResult:
        ...
```

The executor is a method, not a Pydantic field, so it is not serialized. Runtime code must still avoid persisting the `AgentTool` object itself. Sessions and model contexts persist only ordinary `Tool` declarations and messages.

Start `AgentToolResult` with only the fields currently needed:

```python
class AgentToolResult(BaseModel):
    content: list[TextContent | ImageContent]
    details: Any = None
```

Tool execution failures raise exceptions. The loop catches them and creates an error `ToolResultMessage`.

Defer labels, usage, termination hints, dynamic tools, execution modes, tool contexts, and partial-update callbacks.

Tool arguments are validated against the tool's JSON Schema before execution. Add a JSON Schema dependency when this milestone begins rather than implementing a partial validator.

### Lifecycle events

Define Pydantic event models as a discriminated `AgentEvent` union so events can later cross interactive, print, or RPC boundaries.

Initial lifecycle events:

```text
agent_start
agent_end
turn_start
turn_end
message_start
message_update
message_end
tool_execution_start
tool_execution_end
```

Use Pi's minimal payload structure:

- `agent_end` carries messages produced by this run.
- `turn_end` carries the assistant message and ordered tool-result messages.
- Message events carry the current `Message`.
- `message_update` also carries the source `AssistantMessageEvent`.
- Tool events carry the tool-call ID, tool name, arguments, result, and error status as applicable.

Reserve `tool_execution_update` for later. Do not implement partial tool output yet.

Completion tests:

- Construct every tool-result and event model.
- Serialize and deserialize every event variant.
- Reject malformed event discriminators.
- Confirm an `AgentTool` is accepted wherever a model-visible `Tool` is expected.
- Confirm the executor is absent from serialization.
- Validate and reject tool arguments through JSON Schema.

## Milestone 2: sequential low-level loop

Implement `run_agent_loop` as a stateless async generator:

```python
async def run_agent_loop(
    prompts: Sequence[Message],
    *,
    context: Context,
    model: Model,
    providers: ProviderManager,
    tools: Sequence[AgentTool] = (),
    options: StreamOptions | None = None,
) -> AsyncIterator[AgentEvent]:
    ...
```

Also provide `run_agent_loop_continue` for an existing context whose final message is a user or tool-result message.

The loop copies `context.messages` before building its working conversation. It must not mutate the caller's `Context` object.

Executable tools are the source of truth for each model request. Before streaming, the loop derives a model-visible context with those tool declarations:

```python
request_context = working_context.model_copy(
    update={"tools": list(tools)},
)
```

This prevents a separate list of declarations from drifting away from executable tools. Plain chat that needs declared but non-executable tools should use `kiku-ai` directly rather than the agent loop.

The loop resolves the provider through `ProviderManager`:

```python
provider = providers.get_provider(model.provider)
```

An unknown provider becomes a normalized assistant error event sequence. A registered provider is streamed directly:

```python
async for event in provider.stream(model, request_context, options):
    ...
```

There is no separate stream-function protocol, loop configuration object, or event sink. Callers consume events with normal async iteration:

```python
async for event in run_agent_loop(...):
    ...
```

Initial flow:

```text
prompt messages
    ↓
stream assistant response
    ↓
collect tool calls
    ↓
validate and execute tools sequentially
    ↓
append tool results
    ↓
continue with the model or stop
```

Required behavior:

- Emit prompt, assistant, tool, turn, and run lifecycle events in deterministic order.
- Carry all messages produced by the invocation in the terminal `agent_end` event. The async generator has no separate result API.
- Treat the terminal AI event as the final assistant message.
- Convert unknown tools into error tool results.
- Convert invalid arguments into error tool results.
- Convert tool exceptions into error tool results.
- Preserve tool-result order from the assistant message.
- Never execute tool calls from a response stopped by `length` because arguments may be truncated.
- End normally on provider `error` or `aborted` messages while preserving partial content.
- Propagate external asyncio cancellation and close the active provider iterator.
- Continue automatically only when a completed assistant response requested tools.

Keep the loop independent from session persistence and application configuration.

Completion tests:

- Text-only response.
- One tool call followed by a final assistant response.
- Multiple sequential tool calls.
- Unknown tool.
- Invalid arguments.
- Tool exception.
- Length-truncated tool call.
- Provider error.
- Cancellation.
- Exact lifecycle event ordering.

## Milestone 3: stateful `Agent`

Implement a lightweight in-memory wrapper over `run_agent_loop`.

Define `AgentState` here rather than as a low-level loop contract:

```python
@dataclass
class AgentState:
    context: Context
    model: Model
    tools: list[AgentTool]
    is_streaming: bool = False
    streaming_message: AssistantMessage | None = None
    pending_tool_calls: frozenset[str] = frozenset()
    error_message: str | None = None
```

`Context` remains the source of the system prompt and transcript. Its model-visible tool declarations are derived from `AgentState.tools` when a request starts.

`Agent` owns:

- Current `Context`
- Current model
- Executable tools
- Current partial assistant message
- Pending tool-call IDs
- Busy state
- Last error
- Abort handling
- Event subscriptions

Suggested API:

```python
agent = Agent(...)
agent.subscribe(handle_event)
await agent.prompt("Inspect this project")
```

`Agent` consumes the low-level async generator internally:

```python
async for event in run_agent_loop(...):
    agent.reduce(event)
    await agent.notify_subscribers(event)
```

State is reduced before subscribers observe an event. Subscribers are an `Agent` concern, not a low-level `AgentEventSink` contract.

Also support continuation from an existing user or tool-result tail.

Behavioral requirements:

- Reject concurrent `prompt` or `continue_` calls.
- Reduce internal state before notifying subscribers.
- Await subscribers in registration order.
- Append completed messages to `state.context.messages` exactly once.
- Keep the run busy until terminal-event subscribers settle.
- Expose `wait_for_idle()`.
- Make `abort()` cancel the active prompt task and active provider iteration.
- Copy assigned context messages and tool collections at their public mutation boundaries.

Do not add persistence, resources, compaction, or standard coding tools to `Agent`.

Completion tests:

- Default and supplied state.
- Prompt updates context and transient state.
- Subscriber ordering and settlement.
- Concurrent prompt rejection.
- Continue validation.
- Abort and idle settlement.
- Tool pending-state updates.
- Completed messages are appended once.

## Milestone 4: steering and follow-up queues

Add runtime queues to `Agent` and the low-level loop. Introduce direct queue-provider callback arguments only when this milestone begins. Do not create a general loop configuration object for them.

- Steering messages are injected after the current assistant turn and its tools finish.
- Follow-up messages are injected only when the agent would otherwise stop.
- Start with one-at-a-time queue draining.
- Queue clearing is explicit.
- Abort clears steering and follow-up queues.

Do not interrupt an in-flight provider response or skip tools already requested by the completed assistant message.

Completion tests:

- Steering after a tool turn.
- Follow-up after normal completion.
- FIFO behavior.
- Queue clearing.
- Queue behavior around abort and continuation.

## Milestone 5: minimal session and harness

Introduce `AgentHarness` as a session-backed orchestration layer that consumes `run_agent_loop` directly:

```text
AgentHarness
    ├── Session
    └── run_agent_loop
```

It does not construct or wrap `Agent`. This avoids synchronizing `Agent`'s in-memory transcript with a second durable source of truth.

Start with:

- A `SessionStorage` protocol
- An append-only session model
- `MemorySessionStorage`
- Message entries
- Model-change entries
- Thinking-level-change entries
- Active-tools-change entries
- Custom entries
- Idle and turn phases

Session entries should include stable IDs, parent IDs, and timestamps even while the first implementation uses a linear active branch. This leaves room for tree navigation without requiring it now.

The session is the harness's source of truth:

1. Starting a run builds a model `Context` from committed session entries.
2. The harness snapshots the model, system prompt, tools, tool context, and stream options.
3. The harness consumes `run_agent_loop` events directly.
4. Completed messages are persisted on `message_end` before harness subscribers are notified.
5. Reopening the session reconstructs context without serializing executable tools, providers, or callbacks.

The harness owns:

- Session-backed context construction
- Persistence before harness-level message-end notifications
- Model, thinking-level, and active-tool configuration entries
- System prompt as a string or run-start provider
- Tool context as a value or run-start provider
- Harness queues and abort behavior
- Prevention of concurrent structural operations

`Agent` independently owns equivalent transient behavior for its in-memory API. Shared private helpers may be extracted when duplication becomes concrete, but `AgentHarness` must not depend on `Agent` state.

For the initial harness, configuration is snapshotted when a run starts. Configuration changes that would affect an active run are rejected or deferred until the run settles. Turn-level save points, pending writes, and mid-run configuration refresh remain later features.

Completion tests:

- Memory-backed prompt and reopen behavior.
- Message persistence order.
- Harness subscribers observe committed message-end state.
- Busy structural-operation rejection.
- Run snapshot isolation.
- Context reconstruction after reopen.
- Custom entries excluded from model context by default.
- Harness queue and abort behavior.

## Milestone 6: JSONL persistence

Add a standard JSONL session backend after the memory session contract is stable.

Implement:

- Create, open, list, and delete
- Append-only writes
- Active leaf persistence
- Context reconstruction
- Basic session metadata

Do not implement recovery of in-flight provider requests or tools. On restart, only committed entries are authoritative.

Completion tests:

- Create and reopen a session.
- Preserve entry and leaf order.
- Reject malformed entries with typed storage errors.
- Isolate sessions by ID and path.

## Milestone 7: execution capabilities and standard tools

Add runtime-neutral filesystem and shell protocols, then a local Python adapter.

Implement standard tools only as the Kiku application needs them, in this order:

1. Read
2. Write
3. Edit
4. Shell

Standard tools receive an execution context instead of importing process-wide filesystem or subprocess behavior directly.

The application continues to own:

- Working-directory selection
- Environment inheritance policy
- Approval policy
- Sandboxing policy
- Application-specific tools

Add a narrow `before_tool_call` hook for approval and blocking. Add `after_tool_call` only when a concrete result-transformation need appears.

## Milestone 8: resources and prompt construction

Add only when consumed by the application:

- Skill model and parser
- Prompt-template model and formatter
- System-prompt construction helpers
- Resource collections on harness run snapshots

`kiku-agent` owns reusable parsing and formatting. The application owns discovery paths, precedence, provenance, watching, and reload policy.

## Milestone 9: context management

Add when real sessions approach context limits:

- Token estimation
- Compaction preparation
- Summary generation through `kiku-ai`
- Compaction session entries
- Context projection from compacted branches
- Manual compaction operation

Automatic compaction, branch navigation, and branch summaries remain separate later work.

## Deferred work

Do not implement these until a concrete Kiku requirement appears:

- Parallel tool execution
- Partial tool-result streaming
- Per-tool execution mode overrides
- Generic hook reducers and provenance
- Durable queues or pending writes
- Turn-level save points and mid-run configuration refresh
- In-flight provider recovery
- Automatic retry of unfinished tools
- Tool idempotency metadata
- Session branch navigation
- Branch summaries
- SQLite storage
- Automatic compaction
- Compaction retry policies
- Dynamic tools returned by tool results
- Runtime proxy transports
- RPC-specific behavior
- Multiple operating-system adapters

## First usable release

The first independently useful release ends after Milestone 4:

```text
fake tool-call streaming
    ↓
sequential run_agent_loop
    ↓
stateful Agent
    ↓
steering and follow-up queues
```

It provides a complete in-memory agent without coupling ordinary use to sessions or the coding harness.

The first Kiku coding-agent release then adds Milestones 5 through 7 incrementally: memory sessions, JSONL persistence, execution capabilities, and only the standard tools the application actually uses.
