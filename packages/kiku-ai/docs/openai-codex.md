# OpenAI Codex integration

## Goal

OpenAI Codex is the first real provider target because Kiku's initial user already has access through a ChatGPT subscription.

Codex subscription access is not the same as the standard OpenAI API-key service. It uses ChatGPT OAuth credentials and a Codex-specific Responses endpoint.

## Pi provider definition

Pi defines:

```text
provider ID: openai-codex
API ID:      openai-codex-responses
base URL:    https://chatgpt.com/backend-api
```

The Responses endpoint resolves to:

```text
https://chatgpt.com/backend-api/codex/responses
```

Pi source:

- `packages/ai/src/providers/openai-codex.ts`
- `packages/ai/src/api/openai-codex-responses.ts`

## Required authentication data

A Codex credential needs:

- OAuth access token
- OAuth refresh token
- Expiration time
- ChatGPT account ID

Pi extracts the account ID from a JWT claim named `chatgpt_account_id` in the token's authentication claims.

The request uses headers including:

```text
Authorization: Bearer <access token>
chatgpt-account-id: <account ID>
OpenAI-Beta: responses=experimental
Accept: text/event-stream
Content-Type: application/json
```

Pi also sends an originator and user-agent header. Kiku should use its own accurate identity rather than copying Pi's `originator: pi` value.

## Staged implementation

### Stage 1: fake provider

Build and test the normalized domain and streaming contracts without network access.

### Stage 2: pure request serializer

Create:

```text
src/kiku_ai/api/openai_codex_responses.py
```

Start with a pure function:

```python
def build_request(
    model: Model,
    context: Context,
    options: StreamOptions,
) -> dict[str, Any]: ...
```

Test the generated request body directly.

### Stage 3: SSE parser

Implement SSE before WebSockets:

```python
async def parse_codex_events(
    response: httpx.Response,
) -> AsyncIterator[AssistantMessageEvent]: ...
```

Test against local SSE fixtures. Fixtures should cover:

- Text response
- Reasoning summary
- Tool call with partial JSON
- Usage metadata
- Normal stop
- Tool-use stop
- Provider error
- Truncated stream

### Stage 4: injected credential integration

Allow tests or local experiments to supply an access token and account ID directly:

```python
provider = OpenAICodexProvider(
    access_token=token,
    account_id=account_id,
)
```

This validates the HTTP adapter before building the login flow.

Secrets must never be committed to fixtures or logs.

### Stage 5: OAuth

Implement:

- PKCE authorization
- Browser callback or device-code interaction
- Authorization-code exchange
- Refresh-token exchange
- Credential persistence
- Account-ID extraction
- Serialized token refresh
- Logout

### Stage 6: advanced transport

Only after SSE is stable, consider:

- WebSocket transport
- Session-based WebSocket reuse
- Cached input deltas
- Automatic SSE fallback
- Request compression

These are performance and resilience features, not prerequisites for initial model support.

## Recommended HTTP dependency

`httpx.AsyncClient` is used because it supports asynchronous requests and streamed response bodies. The fake provider does not depend on `httpx`.

The initial SSE adapter attempts each request once. The provider-neutral `max_retries` and `max_retry_delay_seconds` stream options are currently ignored by this adapter. Retry behavior should be added only with tests that prevent replay after partial output has already been emitted.

An HTTP mocking library such as `respx` can be introduced with the real adapter tests.

## Initial scope

The first real Codex version should support:

- SSE transport
- Text output
- Reasoning output
- Tool declarations
- Tool-call streaming
- Tool-result replay
- Usage data
- Cancellation
- Explicit injected credentials

It should not initially support:

- WebSockets
- Connection caching
- Dynamic model catalogs
- Every service-tier option
- Request compression
- Automatic OAuth login

## Pi implementation warning

Pi's Codex adapter is large because it includes retries, multiple transports, session affinity, cached WebSockets, response replay, compression, compatibility handling, and detailed errors. Kiku should reproduce the protocol contract in small stages rather than porting the file wholesale.

## Pi design source

- `packages/ai/src/providers/openai-codex.ts`
- `packages/ai/src/providers/openai-codex.models.ts`
- `packages/ai/src/api/openai-codex-responses.lazy.ts`
- `packages/ai/src/api/openai-codex-responses.ts`
- `packages/ai/src/auth/oauth/openai-codex.ts`
