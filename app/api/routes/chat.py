"""`POST /chat` (SSE) and `POST /chat/sync` (JSON) — design.md "Decision: Two
endpoints, one path" and "Decision: Two error windows".

Both routes depend on the exact same `app.api.service.run_turn()` guarded
generator via `Depends(get_agent)` / `Depends(get_thread_registry)`
(PR 1's `app/api/dependencies.py`) — this module never reimplements
guardrail logic, it only adapts `AgentEvent`s to a transport (spec:
"Chat Endpoint Contracts" — "the system MUST NOT maintain divergent
guardrail logic per endpoint").

The two-window error contract lives here, not in `run_turn()` itself:
`run_turn()` only ever raises `ProviderUnavailableError` /
`AgentExecutionError` (never a bare exception) for a failure that survives
its own try/except. `/chat` peeks the first event before returning
`StreamingResponse` — a failure on that first pull is a plain exception
propagating out of this route function, so FastAPI dispatches it to the
centralized `@app.exception_handler`s registered in `app/api/errors.py` ->
HTTP 502/503, no stream ever opened. A failure on a *later* pull happens
strictly after `StreamingResponse` has already committed the SSE headers,
so `_sse_body` must catch it itself and emit a terminal `error` frame
instead (the status code can no longer change).
"""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import ThreadRegistry, get_agent, get_thread_registry
from app.api.errors import AgentExecutionError, ProviderUnavailableError
from app.api.events import AgentEvent, BlockedEvent, ContentEvent, DoneEvent, ErrorEvent
from app.api.schemas import ChatRequest, ChatResponse
from app.api.service import run_turn
from app.api.sse import format_sse

router = APIRouter()


async def _sse_body(first_event: AgentEvent, rest: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    """Yield `first_event` (already pulled by `chat()` to decide the
    pre-first-byte HTTP window), then drain `rest`. Any exception raised
    while draining `rest` happens strictly after `StreamingResponse` has
    already written the SSE headers, so it is converted into a terminal
    `error` frame here instead of propagating (design.md "Decision: Two
    error windows" — the post-first-byte window)."""
    yield format_sse(first_event)
    try:
        async for event in rest:
            yield format_sse(event)
    except (ProviderUnavailableError, AgentExecutionError) as exc:
        yield format_sse(ErrorEvent(code=exc.code, message=exc.safe_message))


@router.post("/chat")
async def chat(
    request: ChatRequest,
    agent=Depends(get_agent),
    registry: ThreadRegistry = Depends(get_thread_registry),
) -> StreamingResponse:
    """SSE endpoint (spec: "Chat Endpoint Contracts" table — `text/event-stream`,
    `progress`/`content` events then one terminal event). Peeking the first
    event here, before constructing `StreamingResponse`, is what makes the
    pre-first-byte window observable as a real HTTP status: if `run_turn()`
    raises on its very first `__anext__()` (e.g. the provider call itself
    failed before yielding anything), that exception propagates out of this
    async function exactly like any other route-level exception, straight to
    the centralized handlers -> HTTP 502/503."""
    events = run_turn(request, agent, registry)
    first_event = await events.__anext__()
    return StreamingResponse(_sse_body(first_event, events), media_type="text/event-stream")


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(
    request: ChatRequest,
    agent=Depends(get_agent),
    registry: ThreadRegistry = Depends(get_thread_registry),
) -> ChatResponse:
    """Non-streaming JSON endpoint (spec: "Chat Endpoint Contracts" table —
    HTTP 200 `{content, thread_id, status}`). Folds `run_turn()`'s events
    into one `ChatResponse`: `content` events concatenate; a terminal
    `blocked` event REPLACES all prior content with its safe message
    (mirrors the SSE REPLACE semantic — spec: "Blocked-Turn Replace
    Semantics" — even on the non-streaming transport). There is only one
    error window here: any exception propagates straight to the centralized
    handlers -> HTTP 502/503, since no partial body has been sent yet on a
    plain (non-streaming) JSON response.
    """
    content_parts: list[str] = []
    thread_id = request.thread_id
    status = "ok"

    async for event in run_turn(request, agent, registry):
        if isinstance(event, ContentEvent):
            content_parts.append(event.text)
        elif isinstance(event, BlockedEvent):
            content_parts = [event.message]
            status = "blocked"
        elif isinstance(event, DoneEvent):
            thread_id = event.thread_id
            status = event.status

    return ChatResponse(content="".join(content_parts), thread_id=thread_id, status=status)
