"""`AgentEvent` -> SSE frame serializer (design.md Interfaces/Contracts).

One pure function, no FastAPI import: `format_sse()` turns any `AgentEvent`
into a single `text/event-stream` frame. `app/api/routes/chat.py` (PR 2)
wraps `run_turn()`'s async generator with this to build the
`StreamingResponse` body; nothing here knows about HTTP.

Frame shape:

    event: <type>\\n
    data: <json>\\n
    \\n

`data:` is always exactly one `json.dumps(...)` call with no `indent` (so
the JSON text itself can never contain a literal newline — a multi-line
`data:` payload would otherwise have to be split across repeated `data:`
lines per the SSE spec, which this protocol deliberately avoids by keeping
every event's payload single-line JSON).
"""

from __future__ import annotations

import json

from app.api.events import AgentEvent, BlockedEvent, ContentEvent, DoneEvent, ErrorEvent, ProgressEvent


def _payload(event: AgentEvent) -> dict:
    """Map one `AgentEvent` to its JSON-serializable `data:` body, per
    design.md's Interfaces/Contracts table. Exhaustive over the 5 known
    event types; an unrecognized type is a programming error, not a
    runtime condition to swallow — it raises loudly."""
    if isinstance(event, ProgressEvent):
        return {"label": event.label}
    if isinstance(event, ContentEvent):
        return {"text": event.text}
    if isinstance(event, BlockedEvent):
        return {"message": event.message, "replace": event.replace}
    if isinstance(event, ErrorEvent):
        return {"code": event.code, "message": event.message, "replace": event.replace}
    if isinstance(event, DoneEvent):
        return {"thread_id": event.thread_id, "status": event.status}
    raise TypeError(f"Unknown AgentEvent type: {type(event)!r}")


def format_sse(event: AgentEvent) -> str:
    """Serialize one `AgentEvent` into a complete SSE frame, ready to write
    to a `StreamingResponse` body as-is (already ends in the blank line
    that terminates an SSE event)."""
    data = json.dumps(_payload(event), ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.type}\ndata: {data}\n\n"
