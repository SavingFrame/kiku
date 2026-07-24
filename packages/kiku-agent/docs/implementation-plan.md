# kiku-agent implementation plan

## Goal

Build the smallest agent runtime needed by Kiku while preserving the boundaries that let it grow into a reusable coding-agent harness.

The package follows Pi's three-layer structure:

```text
AgentHarness
    ↓
Agent              optional lightweight in-memory API
    ↓
run_agent_loop     stateless execution algorithm
    ↓
kiku-ai
```

`AgentHarness` may call `run_agent_loop` directly when it needs precise persistence and save-point ordering. `Agent` remains a useful standalone API for callers that do not need sessions or harness features.

## Design rules

- Keep model protocols, messages, tool declarations, and provider streaming in `kiku-ai`.
- Keep tool execution and continuation in `kiku-agent`.
- Separate transient `Agent` state from durable harness state.
- Use protocols at side-effect boundaries: model streaming, tools, session storage, filesystem access, and process execution.
- Snapshot configuration at turn boundaries. Changes must not mutate an in-flight provider request.
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
│   ├── types.py
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

## Milestone 0: unblock deterministic agent tests

Extend `kiku-ai`'s fake API adapter to stream all content needed by an agent loop:

- Thinking content
- Tool calls
- Tool-call start, delta, and end events
- Responses containing both text and tool calls
- Multiple scripted responses whose factories can inspect accumulated context

Update stale `kiku-ai` documentation that still describes the removed `stream.result()` API.

Completion tests:

- Script a tool-use assistant response.
- Observe final validated tool arguments.
- Follow it with a second scripted assistant response.
- Assert the second response factory receives the first assistant message and its tool result.

## Milestone 1: runtime contracts

Implement the minimum shared contracts:

- `AgentMessage`, initially the model-visible `kiku-ai` message union
- `AgentTool`
- `AgentToolResult`
- `AgentContext`
- `AgentLoopConfig`
- `AgentState`
- `StreamFunction`
- `AgentEvent`

`AgentTool` combines a serializable `kiku_ai.Tool` declaration with an async executor. Executable callbacks are runtime dependencies and must never be serialized into conversation or session data.

Tool arguments are validated against the declaration's JSON Schema before execution. Add a JSON Schema dependency when this milestone begins rather than implementing a partial validator.

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

Reserve `tool_execution_update` for later. Do not implement partial tool output yet.

Completion tests:

- Construct each contract.
- Reject malformed event discriminators where applicable.
- Confirm an executable tool can produce a model-visible tool declaration.
- Validate and reject tool arguments through JSON Schema.

## Milestone 2: sequential low-level loop

Implement `run_agent_loop` as the stateless execution kernel.

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

`Agent` owns:

- System prompt
- Current model
- Tools
- Conversation transcript
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

Also support continuation from an existing user or tool-result tail.

Behavioral requirements:

- Reject concurrent `prompt` or `continue_` calls.
- Reduce internal state before notifying subscribers.
- Await subscribers in registration order.
- Keep the run busy until terminal-event subscribers settle.
- Expose `wait_for_idle()`.
- Make `abort()` cancel the active run.
- Keep assigned tool and message collections isolated from later top-level replacement by callers.

Do not add persistence, resources, compaction, or standard coding tools to `Agent`.

Completion tests:

- Default and supplied state.
- Prompt updates transcript and transient state.
- Subscriber ordering and settlement.
- Concurrent prompt rejection.
- Continue validation.
- Abort and idle settlement.
- Tool pending-state updates.

## Milestone 4: steering and follow-up queues

Add runtime queues to `Agent` and the low-level loop:

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

Introduce `AgentHarness` above the low-level loop. It may call `run_agent_loop` directly rather than wrapping `Agent`.

Start with:

- A `SessionStorage` protocol
- An append-only session model
- `MemorySessionStorage`
- Message entries
- Model-change entries
- Thinking-level-change entries
- Active-tools-change entries
- Custom entries
- Turn snapshots
- Save points
- Idle and turn phases

Session entries should include stable IDs, parent IDs, and timestamps even while the first implementation uses a linear active branch. This leaves room for tree navigation without requiring it now.

The harness owns:

- Session-backed context construction
- Persistence before message-end notifications
- Deterministic flushing at save points
- Model, thinking-level, and active-tool configuration
- System prompt as a string or turn-snapshot provider
- Tool context as a value or turn-snapshot provider
- Prevention of concurrent structural operations

Configuration changed during a turn applies to the next turn snapshot, never the provider request already in flight.

Completion tests:

- Memory-backed prompt and reopen behavior.
- Message persistence order.
- Busy structural-operation rejection.
- Turn snapshot isolation.
- Configuration refresh at save points.
- Custom entries excluded from model context by default.

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
- Resource collections on harness turn snapshots

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
