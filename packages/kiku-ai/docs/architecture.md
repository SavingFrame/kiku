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

Depends on `kiku-ai` and provides two layers.

#### Agent runtime

The runtime owns:

- Agent messages and state
- Executable tool interfaces
- Tool argument validation before execution
- Sequential and parallel tool execution
- Automatic model continuation after tool results
- Agent lifecycle events
- Abort behavior
- Steering and follow-up queues
- Context transformation hooks

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

#### Agent harness

The harness is reusable orchestration above the low-level loop. It owns:

- Session abstractions, session trees, and standard storage implementations
- Turn snapshots and save-point semantics
- Persistence ordering for messages and runtime configuration changes
- Compaction and branch summarization
- Model, thinking-level, tool, and resource configuration for a session
- Active-tool selection
- System-prompt construction hooks
- Skills and prompt-template models, parsing, and formatting
- Extension-facing lifecycle hooks and events
- Runtime-neutral filesystem and shell capability interfaces
- Standard coding tools implemented through those capabilities, such as read, write, edit, and shell execution
- Generic output truncation and tool-result formatting utilities

The harness may provide runtime-specific adapters through explicit submodules or separate packages. Importing the platform-neutral core should not pull in operating-system-specific dependencies.

The harness does not persist executable callbacks, model providers, authentication providers, or extension handlers. The application recreates those runtime dependencies when opening a session.

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

- CLI commands and command routing
- Application configuration and discovery rules
- Credential persistence and login workflows
- Provider and model composition
- Session creation, selection, and resume workflows
- Concrete extension loading and lifecycle
- Resource discovery, precedence, provenance, and reload policy
- Application-specific tools and tool approval policy
- Agent-specific terminal components
- Interactive, print, and RPC modes

The application supplies runtime dependencies to the agent harness. Reusable agent behavior should move into `kiku-agent`; application workflow and presentation should remain outside it.

## Dependency direction

```text
kiku-ai  ←  kiku-agent

kiku-tui has no dependency on kiku-ai or kiku-agent

kiku application  →  all three packages
```

Optional runtime adapters may depend on `kiku-agent`, but the platform-neutral agent core must not depend on them.

Circular dependencies should not be introduced. In particular, `kiku-ai` must never import `kiku-agent` to execute a tool.

## Pi design source

Kiku follows Pi's current high-level split:

```text
@earendil-works/pi-ai
    ↑
@earendil-works/pi-agent-core
    ├── low-level agent runtime
    └── reusable agent harness

@earendil-works/pi-tui

@earendil-works/pi-coding-agent depends on all three
```

The important boundary is between reusable agent capabilities and application policy, not between generic chat and every coding-related capability. Pi's agent package includes runtime-neutral sessions, compaction, resources, execution capabilities, and standard coding tools. The coding application supplies concrete runtime dependencies and owns workflows, extension loading, configuration precedence, and presentation.

Relevant Pi files:

- `packages/ai/package.json`
- `packages/agent/package.json`
- `packages/tui/package.json`
- `packages/coding-agent/package.json`
- `packages/agent/src/agent-loop.ts`
- `packages/agent/src/agent.ts`
- `packages/agent/src/harness/agent-harness.ts`
- `packages/agent/src/harness/types.ts`
- `packages/agent/docs/agent-harness.md`
- `packages/agent/docs/durable-harness.md`

See [Pi source map](pi-source-map.md) for the earlier pinned architectural baseline. The harness boundary above was reviewed against the current Pi repository as well.
