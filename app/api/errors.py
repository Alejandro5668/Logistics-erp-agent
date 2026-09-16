"""Typed service-layer exceptions + centralized FastAPI exception handlers
(design.md "Decision: Two error windows").

`app.api.service.run_turn()` classifies every failure that survives its own
try/except into one of the two typed exceptions below and re-raises —
never a bare `Exception`, never the provider's own exception type, so the
generic client-safe message and HTTP status are decided in exactly one
place regardless of which provider SDK is wired in later.

The router (`app/api/routes/chat.py`, PR 2) owns the two-window contract:
it peeks the first event from `run_turn()` before returning
`StreamingResponse`. A failure on that first pull propagates here as a
normal FastAPI exception -> `@app.exception_handler` -> HTTP 502/503, no
stream ever opened. A failure on a *later* pull happens after headers are
already committed, so the router must catch it itself and emit a terminal
SSE `error` event instead (the status code can no longer change) — these
handlers are for the pre-first-byte window only.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorResponse

# Deliberately distinct from app.security's blocked-turn safe message
# ("I cannot assist with that request.") — that text means "policy denied
# this request"; these mean "the service itself failed". Conflating the two
# would mislead a caller into thinking a transient outage is a guardrail
# block, or vice versa.
_PROVIDER_SAFE_MESSAGE = "The assistant is temporarily unavailable. Please try again shortly."
_AGENT_SAFE_MESSAGE = "Something went wrong while processing your request. Please try again."


class ProviderUnavailableError(Exception):
    """The LLM provider failed: timeout, rate limit, auth, or network
    (spec: "Failure Handling and Checkpointer Safety"). Never constructed
    with provider-internal text — `message` defaults to the generic,
    client-safe string; pass `cause` to keep the original exception
    chained (`raise ProviderUnavailableError() from exc`) for server-side
    logs only, never echoed to the client.
    """

    code = "provider_unavailable"
    http_status = 503

    def __init__(self, message: str = _PROVIDER_SAFE_MESSAGE) -> None:
        super().__init__(message)
        self.safe_message = message


class AgentExecutionError(Exception):
    """An unexpected LangGraph graph/tool-node error, distinct from F-B1's
    own never-raises tool contract (E4: `ToolNode`'s default error handler
    already turns a tool exception into a `ToolMessage(status="error")`
    that never reaches here — this is for failures LangGraph itself cannot
    absorb, e.g. a graph-execution error). Same generic-message contract as
    `ProviderUnavailableError`.
    """

    code = "agent_error"
    http_status = 502

    def __init__(self, message: str = _AGENT_SAFE_MESSAGE) -> None:
        super().__init__(message)
        self.safe_message = message


def _error_response(exc: ProviderUnavailableError | AgentExecutionError) -> JSONResponse:
    body = ErrorResponse(code=exc.code, message=exc.safe_message, replace=True)
    return JSONResponse(status_code=exc.http_status, content=body.model_dump())


async def provider_unavailable_handler(request: Request, exc: ProviderUnavailableError) -> JSONResponse:
    """`@app.exception_handler(ProviderUnavailableError)` — HTTP 503, generic body."""
    return _error_response(exc)


async def agent_execution_error_handler(request: Request, exc: AgentExecutionError) -> JSONResponse:
    """`@app.exception_handler(AgentExecutionError)` — HTTP 502, generic body."""
    return _error_response(exc)


# `app/api/app.py` (PR 2) registers both via
# `app.add_exception_handler(ProviderUnavailableError, provider_unavailable_handler)`.
EXCEPTION_HANDLERS = {
    ProviderUnavailableError: provider_unavailable_handler,
    AgentExecutionError: agent_execution_error_handler,
}
