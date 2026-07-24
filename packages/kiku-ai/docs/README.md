# Kiku AI design documentation

These documents describe the planned design of `kiku-ai`, based on the architecture of Pi's `@earendil-works/pi-ai` package.

The Pi source was inspected at commit [`65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a`](https://github.com/earendil-works/pi/tree/65ff8e7f6db447dcddb1a9c8fd05f081c5cda76a).

These are design notes, not a description of completed Kiku functionality. When Kiku intentionally differs from Pi, the difference should be recorded in the relevant document.

## Documents

- [Architecture](architecture.md): Package boundaries and dependency direction
- [Domain model](domain-model.md): `Context`, messages, content blocks, tools, models, usage, and stop reasons
- [Streaming](streaming.md): Normalized events and the final-result stream contract
- [Providers and APIs](providers-and-apis.md): Provider registry, authentication, and reusable wire-protocol adapters
- [OpenAI Codex](openai-codex.md): Target integration, constraints, and staged implementation
- [Implementation plan](implementation-plan.md): Small testable milestones beginning with a faux provider
- [Pi source map](pi-source-map.md): Exact upstream files from which the design was derived

## Intended package graph

```text
kiku-ai        no Kiku package dependencies
    ↑
kiku-agent     depends on kiku-ai

kiku-tui       generic and independent

kiku app       depends on kiku-ai, kiku-agent, and kiku-tui
```

`kiku-ai` communicates with models and normalizes their output. It describes tools but does not execute them. `kiku-agent` owns tool execution and the multi-turn agent loop. `kiku-tui` owns generic terminal rendering and input.

## Suggested questions for later sessions

- "What is the Context model in `packages/kiku-ai/docs/domain-model.md`?"
- "What is the next unfinished milestone in `packages/kiku-ai/docs/implementation-plan.md`?"
- "How should a provider differ from an API adapter?"
- "What must be implemented before real OpenAI Codex OAuth?"
