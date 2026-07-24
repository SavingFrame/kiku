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

Several providers can share one API adapter. This avoids duplicating message conversion and stream parsing for every OpenAI-compatible service. Provider implementations live under `kiku_ai.providers`; wire adapters and their protocol-specific helpers live under `kiku_ai.api`.

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
    api: ApiAdapter
    base_url: str

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

Base interface:

```python
class ApiAdapter(Protocol):
    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
        *,
        auth: ModelAuth,
        base_url: str,
    ) -> AssistantMessageStream: ...
```

The provider resolves authentication before invoking its adapter. `ModelAuth` and `base_url` are keyword-only so credentials and provider transport configuration cannot be confused with canonical request data. The adapter receives no credential store and does not resolve or persist credentials. It combines auth headers, protocol defaults, and request-level options when constructing the wire request.

`base_url` belongs to the provider rather than `Model` or `ModelAuth`. Models identify their wire protocol through `Model.api`, while the provider owns both the adapter implementation and its endpoint. The initial contract uses one adapter per provider; a mapping keyed by `Model.api` should only be introduced when a concrete mixed-API provider requires it.

Like `Provider.stream()`, the adapter method returns a stream synchronously. Asynchronous HTTP work and failures are produced behind that stream. A provider that needs asynchronous authentication can return an outer stream, resolve auth in a task, then forward the adapter's stream. This follows Pi's lazy stream setup pattern without moving orchestration into the adapter.

## Provider manager

`ProviderManager` is only a registry and model lookup facade:

```python
class ProviderManager:
    def register(self, provider: Provider) -> None: ...
    def unregister(self, provider_id: str) -> None: ...
    def get_provider(self, provider_id: str) -> Provider | None: ...
    def get_models(self, provider_id: str | None = None) -> Sequence[Model]: ...
    def get_model(self, provider_id: str, model_id: str) -> Model | None: ...
```

Authentication and streaming remain provider responsibilities:

```text
provider_manager.get_provider(model.provider)
    ↓
provider.stream(model, context, options)
    ↓
provider resolves authentication
    ↓
provider selects adapter using model.api
    ↓
adapter.stream(
    model,
    context,
    options,
    auth=resolved_auth,
    base_url=provider.base_url,
)
```

`Model` remains serializable metadata and does not perform network requests.

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

Each provider coordinates authentication through its `ProviderAuth` and credential store. This is especially important for expiring OAuth tokens.

The desired precedence is:

```text
explicit request credentials
    ↓
stored provider credential
    ↓
provider-specific environment or ambient credentials
```

For OAuth, refresh should be serialized so concurrent requests do not refresh and rotate the same token more than once.

OAuth is not required for the first fake-provider milestone.

## Current Kiku interface

The current `BaseProvider.stream_response()` takes raw strings and untyped lists. The target design should replace these with:

```python
model: Model
context: Context
options: StreamOptions | None
```

`aclose()` should be declared with `async def` if implementations close asynchronous HTTP clients.

## Pi design source

Pi combines provider management, model lookup, authentication, and streaming convenience in its `Models` object. Kiku intentionally uses `ProviderManager` and leaves streaming on `Provider`.

- `packages/ai/src/models.ts`
- `packages/ai/src/types.ts`
- `packages/ai/src/providers/anthropic.ts`
- `packages/ai/src/api/anthropic-messages.ts`
- `packages/ai/src/api/lazy.ts`
