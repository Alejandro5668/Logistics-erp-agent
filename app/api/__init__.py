"""FastAPI HTTP layer package (F-B6).

PR 1 scope only: schemas, the framework-free `AgentEvent` union, typed
errors, `Depends()` providers, the guarded sink (`run_turn`), and the SSE
serializer. `app/api/routes/`, `app/api/app.py`, and `app/main.py` are PR 2
(chained delivery, see openspec/changes/f-b6-fastapi/tasks.md) and are not
re-exported here yet.
"""

from app.api.dependencies import ThreadRegistry, get_agent, get_thread_registry
from app.api.errors import AgentExecutionError, ProviderUnavailableError
from app.api.events import AgentEvent, BlockedEvent, ContentEvent, DoneEvent, ErrorEvent, ProgressEvent
from app.api.schemas import ChatRequest, ChatResponse, ErrorResponse
from app.api.service import run_turn
from app.api.sse import format_sse

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "ErrorResponse",
    "AgentEvent",
    "ProgressEvent",
    "ContentEvent",
    "BlockedEvent",
    "ErrorEvent",
    "DoneEvent",
    "ProviderUnavailableError",
    "AgentExecutionError",
    "ThreadRegistry",
    "get_agent",
    "get_thread_registry",
    "run_turn",
    "format_sse",
]
