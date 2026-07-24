# Architecture

## Goal

`kiku-ai` provides one provider-neutral interface for tool-capable language models. Applications should be able to change providers without rewriting their conversation state, tool declarations, event handling, or usage accounting.

The package should support ordinary chat independently of the agent runtime and terminal UI.

## Package responsibilities

### `kiku-ai`

Owns:

- Canonical message and content models
- Model metadata
- Conversation `Context`
- Tool declarations and argument schemas
- Normalized streaming events
- Provider registration and model lookup
- Authentication resolution
- Wire-protocol adapters
- Usage and cost accounting
- Provider compatibility transformations

Does not own:

- Tool execution
- Agent continuation loops
- Steering and follow-up queues
- Session compaction policy
- Terminal rendering
- Application commands

### `kiku-agent`

Depends on `kiku-ai` and owns:

- Agent state
- Executable tool interface
- Tool argument validation before execution
- Sequential or parallel tool execution
- Automatic model continuation after tool results
- Agent lifecycle events
- Abort behavior
- Steering and follow-up messages
- Context transformation and compaction hooks

The basic loop is:

```text
user message
    ↓
stream assistant message through kiku-ai
    ↓
collect tool calls
    ↓
validate and execute tools
    ↓
append ToolResultMessage values
    ↓
request the next assistant turn
```

### `kiku-tui`

Should remain generic and own:

- Terminal abstraction
- Differential rendering
- Input decoding
- Focus management
- Text editor and reusable components
- ANSI-aware width, wrapping, and truncation

Agent-specific components, such as an assistant response view or tool execution view, should live in the application package.

### Kiku application

The application composes all packages and owns:

- CLI commands
- Configuration
- Credential persistence
- Concrete coding tools
- Agent-specific terminal components
- Session selection and application workflows

## Dependency direction

```text
kiku-ai  ←  kiku-agent

kiku-tui has no dependency on kiku-ai or kiku-agent

kiku application  →  all three packages
```

Circular dependencies should not be introduced. In particular, `kiku-ai` must never import `kiku-agent` to execute a tool.

## Pi design source

Pi uses the same high-level split:

```text
@earendil-works/pi-ai
    ↑
@earendil-works/pi-agent-core

@earendil-works/pi-tui

@earendil-works/pi-coding-agent depends on all three
```

Relevant Pi files:

- `packages/ai/package.json`
- `packages/agent/package.json`
- `packages/tui/package.json`
- `packages/coding-agent/package.json`
- `packages/agent/src/agent-loop.ts`

See [Pi source map](pi-source-map.md) for pinned links.
