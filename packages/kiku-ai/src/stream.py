import asyncio
from collections.abc import AsyncIterator

from events import AssistantMessage, AssistantMessageEvent


class AssistantMessageStream:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[AssistantMessageEvent] = asyncio.Queue()
        self._result: AssistantMessage | None = None
        self._result_ready = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[AssistantMessageEvent]:
        while True:
            event = await self.queue.get()
            yield event

            if event.type in ("done", "error"):
                return

    async def result(self) -> AssistantMessage:
        await self._result_ready.wait()
        assert self._result is not None
        return self._result

    def push(self, event: AssistantMessageEvent) -> None:
        if self._result_ready.is_set():
            return

        self.queue.put_nowait(event)

        if event.type == "done":
            self._result = event.message
            self._result_ready.set()
        elif event.type == "error":
            self._result = event.error
            self._result_ready.set()
