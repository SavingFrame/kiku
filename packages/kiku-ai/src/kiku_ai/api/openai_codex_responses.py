import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from kiku_ai.auth import ModelAuth
from kiku_ai.context import Context, Tool
from kiku_ai.events import (
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    StartEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from kiku_ai.messages import (
    AssistantMessage,
    ImageContent,
    StopReason,
    TextContent,
    ThinkingContent,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from kiku_ai.models import Model
from kiku_ai.streaming import ReasoningLevel, StreamOptions

_DEFAULT_INSTRUCTIONS = "You are a helpful assistant."
_CODEX_RESPONSES_PATH = "/codex/responses"
_USER_AGENT = "kiku-ai/0.1.0"


@dataclass
class _OutputSlot:
    kind: str
    content_index: int
    arguments_json: str = ""


class OpenAICodexResponsesAdapter:
    """OpenAI Codex Responses adapter using the SSE HTTP transport."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
        *,
        auth: ModelAuth,
        base_url: str,
    ) -> AsyncIterator[AssistantMessageEvent]:
        async def iterator() -> AsyncIterator[AssistantMessageEvent]:
            output = AssistantMessage(
                timestamp=datetime.now(UTC),
                content=[],
                usage=Usage(),
            )
            yield StartEvent(partial=_snapshot(output))

            try:
                if self._client is None:
                    async with httpx.AsyncClient() as client:
                        async for event in self._request_events(
                            client, output, model, context, options, auth, base_url
                        ):
                            yield event
                else:
                    async for event in self._request_events(
                        self._client, output, model, context, options, auth, base_url
                    ):
                        yield event
            except Exception as error:
                output.stop_reason = StopReason.ERROR
                output.error_message = str(error)
                yield ErrorEvent(reason=StopReason.ERROR, error=output)

        return iterator()

    async def _request_events(
        self,
        client: httpx.AsyncClient,
        output: AssistantMessage,
        model: Model,
        context: Context,
        options: StreamOptions | None,
        auth: ModelAuth,
        base_url: str,
    ) -> AsyncIterator[AssistantMessageEvent]:
        request_kwargs: dict[str, Any] = {
            "headers": _build_headers(auth, options),
            "json": _build_request(model, context, options),
        }
        if options is not None and options.timeout_seconds is not None:
            request_kwargs["timeout"] = options.timeout_seconds

        url = f"{base_url.rstrip('/')}{_CODEX_RESPONSES_PATH}"
        async with client.stream("POST", url, **request_kwargs) as response:
            if not response.is_success:
                body = (await response.aread()).decode(errors="replace")
                raise RuntimeError(f"Codex request failed with HTTP {response.status_code}: {body}")

            async for event in _process_codex_events(response.aiter_lines(), output):
                yield event


def _build_headers(auth: ModelAuth, options: StreamOptions | None) -> httpx.Headers:
    if not auth.api_key:
        raise ValueError("OpenAI Codex requires an access token")

    headers = httpx.Headers(auth.headers)
    account_id = headers.get("chatgpt-account-id", "").strip()
    if not account_id:
        raise ValueError("OpenAI Codex requires a chatgpt-account-id header")

    for name, value in (options.headers or {}).items() if options else ():
        if value is None:
            if name in headers:
                del headers[name]
        else:
            headers[name] = value

    headers["Authorization"] = f"Bearer {auth.api_key}"
    headers["chatgpt-account-id"] = account_id
    headers["OpenAI-Beta"] = "responses=experimental"
    headers["Accept"] = "text/event-stream"
    headers["Content-Type"] = "application/json"
    headers["Originator"] = "kiku"
    headers["User-Agent"] = _USER_AGENT
    if options and options.session_id:
        headers["session-id"] = options.session_id
        headers["x-client-request-id"] = options.session_id
    return headers


async def _iter_sse_json(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    data_lines: list[str] = []

    async for line in lines:
        if line == "":
            if data_lines:
                data = "\n".join(data_lines)
                data_lines.clear()
                if data == "[DONE]":
                    return
                event = json.loads(data)
                if isinstance(event, dict):
                    yield event
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        data = "\n".join(data_lines)
        if data != "[DONE]":
            event = json.loads(data)
            if isinstance(event, dict):
                yield event


async def _process_codex_events(
    lines: AsyncIterator[str],
    output: AssistantMessage,
) -> AsyncIterator[AssistantMessageEvent]:
    slots: dict[int, _OutputSlot] = {}

    async for event in _iter_sse_json(lines):
        event_type = event.get("type")
        output_index = int(event.get("output_index", 0))

        if event_type == "response.created":
            response = event.get("response") or {}
            output.response_id = response.get("id")
        elif event_type == "response.output_item.added":
            created = _create_output_slot(output_index, event.get("item") or {}, slots, output)
            if created is not None:
                _slot, start_event = created
                yield start_event
        elif event_type in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
            slot = slots.get(output_index)
            if slot and slot.kind == "thinking":
                block = output.content[slot.content_index]
                assert isinstance(block, ThinkingContent)
                delta = str(event.get("delta", ""))
                block.thinking += delta
                yield ThinkingDeltaEvent(
                    content_index=slot.content_index,
                    delta=delta,
                    partial=_snapshot(output),
                )
        elif event_type == "response.reasoning_summary_part.done":
            slot = slots.get(output_index)
            if slot and slot.kind == "thinking":
                block = output.content[slot.content_index]
                assert isinstance(block, ThinkingContent)
                block.thinking += "\n\n"
                yield ThinkingDeltaEvent(
                    content_index=slot.content_index,
                    delta="\n\n",
                    partial=_snapshot(output),
                )
        elif event_type in ("response.output_text.delta", "response.refusal.delta"):
            slot = slots.get(output_index)
            if slot and slot.kind == "text":
                block = output.content[slot.content_index]
                assert isinstance(block, TextContent)
                delta = str(event.get("delta", ""))
                block.content += delta
                yield TextDeltaEvent(
                    content_index=slot.content_index,
                    delta=delta,
                    partial=_snapshot(output),
                )
        elif event_type == "response.function_call_arguments.delta":
            slot = slots.get(output_index)
            if slot and slot.kind == "tool_call":
                delta = str(event.get("delta", ""))
                slot.arguments_json += delta
                block = output.content[slot.content_index]
                assert isinstance(block, ToolCall)
                block.arguments = _try_parse_arguments(slot.arguments_json, block.arguments)
                yield ToolCallDeltaEvent(
                    content_index=slot.content_index,
                    delta=delta,
                    partial=_snapshot(output),
                )
        elif event_type == "response.function_call_arguments.done":
            slot = slots.get(output_index)
            if slot and slot.kind == "tool_call":
                arguments = str(event.get("arguments", slot.arguments_json))
                delta = arguments[len(slot.arguments_json) :] if arguments.startswith(slot.arguments_json) else ""
                slot.arguments_json = arguments
                block = output.content[slot.content_index]
                assert isinstance(block, ToolCall)
                block.arguments = _parse_arguments(arguments)
                if delta:
                    yield ToolCallDeltaEvent(
                        content_index=slot.content_index,
                        delta=delta,
                        partial=_snapshot(output),
                    )
        elif event_type == "response.output_item.done":
            item = event.get("item") or {}
            slot = slots.get(output_index)
            if slot is None:
                created = _create_output_slot(output_index, item, slots, output)
                if created is not None:
                    slot, start_event = created
                    yield start_event
            if slot is not None:
                yield _finish_output_slot(output_index, slot, item, slots, output)
        elif event_type in ("response.completed", "response.incomplete"):
            response = event.get("response") or {}
            _finalize_response(response, event_type, output)
            yield DoneEvent(reason=_done_reason(output.stop_reason), message=output)
            return
        elif event_type == "response.failed":
            response = event.get("response") or {}
            error = response.get("error") or {}
            incomplete_details = response.get("incomplete_details") or {}
            message = error.get("message") or incomplete_details.get("reason") or "Unknown error"
            raise RuntimeError(str(message))
        elif event_type == "error":
            code = event.get("code", "unknown")
            raise RuntimeError(f"Codex error {code}: {event.get('message', 'Unknown error')}")

    raise RuntimeError("OpenAI Codex stream ended before a terminal response event")


def _create_output_slot(
    output_index: int,
    item: dict[str, Any],
    slots: dict[int, _OutputSlot],
    output: AssistantMessage,
) -> tuple[_OutputSlot, AssistantMessageEvent] | None:
    item_type = item.get("type")
    content_index = len(output.content)

    if item_type == "reasoning":
        output.content.append(ThinkingContent(thinking=""))
        slot = _OutputSlot("thinking", content_index)
        event = ThinkingStartEvent(content_index=content_index, partial=_snapshot(output))
    elif item_type == "message":
        output.content.append(TextContent(content=""))
        slot = _OutputSlot("text", content_index)
        event = TextStartEvent(content_index=content_index, partial=_snapshot(output))
    elif item_type == "function_call":
        call_id = str(item.get("call_id", ""))
        item_id = str(item.get("id", ""))
        tool_call_id = f"{call_id}|{item_id}" if item_id else call_id
        arguments_json = str(item.get("arguments", ""))
        output.content.append(
            ToolCall(
                id=tool_call_id,
                name=str(item.get("name", "")),
                arguments=_try_parse_arguments(arguments_json, {}),
            )
        )
        slot = _OutputSlot("tool_call", content_index, arguments_json)
        event = ToolCallStartEvent(content_index=content_index, partial=_snapshot(output))
    else:
        return None

    slots[output_index] = slot
    return slot, event


def _finish_output_slot(
    output_index: int,
    slot: _OutputSlot,
    item: dict[str, Any],
    slots: dict[int, _OutputSlot],
    output: AssistantMessage,
) -> AssistantMessageEvent:
    block = output.content[slot.content_index]

    if slot.kind == "thinking":
        assert isinstance(block, ThinkingContent)
        summary = "\n\n".join(str(part.get("text", "")) for part in item.get("summary") or [])
        content = "\n\n".join(str(part.get("text", "")) for part in item.get("content") or [])
        block.thinking = summary or content or block.thinking
        block.thinking_signature = json.dumps(item, separators=(",", ":"))
        event: AssistantMessageEvent = ThinkingEndEvent(
            content_index=slot.content_index,
            content=block.thinking,
            partial=_snapshot(output),
        )
    elif slot.kind == "text":
        assert isinstance(block, TextContent)
        block.content = "".join(
            str(part.get("text", part.get("refusal", ""))) for part in item.get("content") or []
        ) or block.content
        event = TextEndEvent(
            content_index=slot.content_index,
            content=block.content,
            partial=_snapshot(output),
        )
    elif slot.kind == "tool_call":
        assert isinstance(block, ToolCall)
        arguments = str(item.get("arguments", slot.arguments_json or "{}"))
        block.arguments = _parse_arguments(arguments)
        event = ToolCallEndEvent(
            content_index=slot.content_index,
            tool_call=block.model_copy(deep=True),
            partial=_snapshot(output),
        )
    else:
        raise ValueError(f"Unknown output slot kind: {slot.kind}")

    del slots[output_index]
    return event


def _finalize_response(response: dict[str, Any], event_type: str, output: AssistantMessage) -> None:
    output.response_id = response.get("id") or output.response_id
    usage = response.get("usage") or {}
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    cache_read = int(input_details.get("cached_tokens") or 0)
    cache_write = int(input_details.get("cache_write_tokens") or 0)
    output.usage = Usage(
        input=max(0, int(usage.get("input_tokens") or 0) - cache_read - cache_write),
        output=int(usage.get("output_tokens") or 0),
        cache_read=cache_read,
        cache_write=cache_write,
        reasoning=int(output_details.get("reasoning_tokens") or 0),
    )
    output.stop_reason = StopReason.LENGTH if event_type == "response.incomplete" else StopReason.STOP
    if output.stop_reason == StopReason.STOP and any(isinstance(item, ToolCall) for item in output.content):
        output.stop_reason = StopReason.TOOL_USE


def _done_reason(
    reason: StopReason | None,
) -> Literal[StopReason.STOP, StopReason.LENGTH, StopReason.TOOL_USE]:
    if reason == StopReason.STOP:
        return StopReason.STOP
    if reason == StopReason.LENGTH:
        return StopReason.LENGTH
    if reason == StopReason.TOOL_USE:
        return StopReason.TOOL_USE
    raise ValueError(f"Invalid successful terminal stop reason: {reason}")


def _try_parse_arguments(value: str, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        return _parse_arguments(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback


def _parse_arguments(value: str) -> dict[str, Any]:
    parsed = json.loads(value or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("Tool arguments must be a JSON object")
    return parsed


def _snapshot(message: AssistantMessage) -> AssistantMessage:
    return message.model_copy(deep=True)


def _build_request(
    model: Model,
    context: Context,
    options: StreamOptions | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model.id,
        "store": False,
        "stream": True,
        "instructions": context.system_prompt or _DEFAULT_INSTRUCTIONS,
        "input": _convert_messages(context),
        "text": {"verbosity": "low"},
        "include": ["reasoning.encrypted_content"],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    }

    if context.tools:
        request["tools"] = [_convert_tool(tool) for tool in context.tools]

    if options is None:
        return request

    if options.temperature is not None:
        request["temperature"] = options.temperature
    if options.max_output_tokens is not None:
        request["max_output_tokens"] = options.max_output_tokens
    if options.session_id is not None:
        request["prompt_cache_key"] = options.session_id
    if options.reasoning is not None and options.reasoning != ReasoningLevel.OFF:
        request["reasoning"] = {"effort": str(options.reasoning), "summary": "auto"}

    return request


def _convert_messages(context: Context) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []

    for message_index, message in enumerate(context.messages):
        if isinstance(message, UserMessage):
            converted.extend(_convert_user_message(message))
        elif isinstance(message, AssistantMessage):
            converted.extend(_convert_assistant_message(message, message_index))
        elif isinstance(message, ToolResultMessage):
            converted.append(_convert_tool_result(message))

    return converted


def _convert_user_message(message: UserMessage) -> list[dict[str, Any]]:
    if isinstance(message.content, str):
        content = [{"type": "input_text", "text": message.content}]
    else:
        content = [_convert_input_content(item) for item in message.content]

    if not content:
        return []
    return [{"role": "user", "content": content}]


def _convert_assistant_message(message: AssistantMessage, message_index: int) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    text_index = 0

    for content in message.content:
        if isinstance(content, ThinkingContent):
            if content.thinking_signature is not None:
                converted.append(json.loads(content.thinking_signature))
        elif isinstance(content, TextContent):
            suffix = "" if text_index == 0 else f"_{text_index}"
            converted.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content.content, "annotations": []}],
                    "status": "completed",
                    "id": f"msg_kiku_{message_index}{suffix}",
                }
            )
            text_index += 1
        elif isinstance(content, ToolCall):
            call_id, separator, item_id = content.id.partition("|")
            tool_call: dict[str, Any] = {
                "type": "function_call",
                "call_id": call_id,
                "name": content.name,
                "arguments": json.dumps(content.arguments, separators=(",", ":")),
            }
            if separator and item_id.startswith("fc_"):
                tool_call["id"] = item_id
            converted.append(tool_call)

    return converted


def _convert_tool_result(message: ToolResultMessage) -> dict[str, Any]:
    call_id = message.tool_call_id.partition("|")[0]
    text = "\n".join(item.content for item in message.content if isinstance(item, TextContent))
    images = [item for item in message.content if isinstance(item, ImageContent)]

    if not images:
        output: str | list[dict[str, str]] = text or "(no tool output)"
    else:
        output = []
        if text:
            output.append({"type": "input_text", "text": text})
        output.extend(_convert_image(image) for image in images)

    return {"type": "function_call_output", "call_id": call_id, "output": output}


def _convert_input_content(content: TextContent | ImageContent) -> dict[str, str]:
    if isinstance(content, TextContent):
        return {"type": "input_text", "text": content.content}
    return _convert_image(content)


def _convert_image(content: ImageContent) -> dict[str, str]:
    return {
        "type": "input_image",
        "detail": "auto",
        "image_url": f"data:{content.mime_type};base64,{content.content}",
    }


def _convert_tool(tool: Tool) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
        "strict": None,
    }
