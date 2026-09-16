"""Pydantic request/response models for the F-B6 HTTP layer.

Both `/chat` (SSE) and `/chat/sync` (JSON, PR 2) accept the same
`ChatRequest` and drive the same `app.api.service.run_turn()` guarded
pipeline (spec: "one shared guarded execution pipeline; the system MUST NOT
maintain divergent guardrail logic per endpoint"). `ChatResponse` is the
non-streaming fold of a completed turn's events; `ErrorResponse` is the
generic client-safe body both the pre-first-byte HTTP exception handlers
(`app/api/errors.py`) and the terminal SSE `error` event (`app/api/sse.py`)
serialize from.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """One turn's request body: `{message, thread_id, role}`.

    `role` is forwarded, unverified, as `context={"role": role}` — exactly
    the shape `app.security.middleware._role_from_context` reads (spec:
    "Role and Thread_id Propagation"). Auth/JWT is out of scope for this
    prototype (proposal.md); `role` stays client-supplied and spoofable.
    """

    message: str = Field(..., min_length=1, description="The user's turn text.")
    thread_id: str = Field(..., min_length=1, description="Caller-supplied session id.")
    role: Optional[str] = Field(
        default=None,
        description="Caller-supplied role (e.g. 'ADMIN', 'EMPLOYEE'); unset fails closed.",
    )


class ChatResponse(BaseModel):
    """The non-streaming `/chat/sync` (PR 2) response: a completed turn
    folded to its final guardrail-approved content (or safe message)."""

    content: str
    thread_id: str
    status: str


class ErrorResponse(BaseModel):
    """The generic, client-safe error body. Never carries provider details,
    stack traces, or ERP rows (spec: "Failure Handling and Checkpointer
    Safety"). `replace: true` mirrors the SSE `blocked`/`error` REPLACE
    semantic even in the JSON error path, so both transports agree on shape.
    """

    code: str
    message: str
    replace: bool = True
