# Providers and API adapters

## Provider and API are separate concepts

A provider is the runtime owner of models and authentication. An API adapter implements a wire protocol.

Examples:

```text
Provider: openai-codex
API:      openai-codex-responses

Provider: openrouter
API:      openai-completions

Provider: groq
API:      openai-completions
```

Several providers can share one API adapter. This avoids duplicating message conversion and stream parsing for every OpenAI-compatible service.

## Provider responsibilities

A provider owns:

- Stable ID and display name
- Model catalog
- Authentication strategy
- Optional provider-wide base URL and headers
- Optional dynamic model refresh
- Selection of an API adapter for each model

Target interface:

```python
class Provider(Protocol):
    id: str
    name: str

    def get_models(self) -> Sequence[Model]: ...

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantMessageStream: ...
```

The provider does not execute model-requested tools.

## API adapter responsibilities

An API adapter owns:

- Conversion from canonical messages to provider payloads
- Conversion of JSON Schema tool declarations
- Generic reasoning option translation
- HTTP or SDK request creation
- Streaming response parsing
- Normalized content events
- Usage extraction
- Stop-reason mapping
- Protocol-specific compatibility behavior

Target interface:

```python
class ApiAdapter(Protocol):
    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantMessageStream: ...
```

## Models registry

`Models` is the application-facing runtime registry:

```python
class Models:
    def add_provider(self, provider: Provider) -> None: ...
    def get_provider(self, provider_id: str) -> Provider | None: ...
    def get_models(self, provider_id: str | None = None) -> Sequence[Model]: ...
    def get_model(self, provider_id: str, model_id: str) -> Model | None: ...
    def stream(...) -> AssistantMessageStream: ...
    async def complete(...) -> AssistantMessage: ...
```

Request routing is:

```text
Models.stream(model, context, options)
    ↓
find provider using model.provider
    ↓
resolve authentication
    ↓
provider selects adapter using model.api
    ↓
adapter streams normalized events
```

`complete()` is a convenience around the stream result:

```python
async def complete(...):
    return await self.stream(...).result()
```

## Stream options

Timeouts and retry policy should normally be request options instead of permanent provider configuration:

```python
class StreamOptions(BaseModel):
    temperature: float | None = None
    max_output_tokens: int | None = None
    reasoning: ReasoningLevel | None = None
    timeout_seconds: float | None = None
    max_retries: int | None = None
    max_retry_delay_seconds: float | None = None
    headers: dict[str, str | None] | None = None
    session_id: str | None = None
```

Provider identity, credentials, and static defaults can remain provider configuration.

## Authentication

Authentication should eventually be represented by a separate resolver or credential store. This is especially important for expiring OAuth tokens.

The desired precedence is:

```text
explicit request credentials
    ↓
stored provider credential
    ↓
provider-specific environment or ambient credentials
```

For OAuth, refresh should be serialized so concurrent requests do not refresh and rotate the same token more than once.

OAuth is not required for the first faux-provider milestone.

## Current Kiku interface

The current `BaseProvider.stream_response()` takes raw strings and untyped lists. The target design should replace these with:

```python
model: Model
context: Context
options: StreamOptions | None
```

`aclose()` should be declared with `async def` if implementations close asynchronous HTTP clients.

## Pi design source

- `packages/ai/src/models.ts`
- `packages/ai/src/types.ts`
- `packages/ai/src/providers/anthropic.ts`
- `packages/ai/src/api/anthropic-messages.ts`
- `packages/ai/src/api/lazy.ts`
