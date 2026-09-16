"""Framework-free `AgentEvent` union (design.md "Two endpoints, one path").

`app.api.service.run_turn()` yields these — no FastAPI, no LangChain, no
LangGraph import here. `/chat` (PR 2) serializes them to SSE via
`app/api/sse.py`; `/chat/sync` (PR 2) folds them into a `ChatResponse`. One
guardrail path, two transports (spec: "MUST NOT maintain divergent guardrail
logic per endpoint").

Every event carries a class-level `type` discriminator matching the SSE
`event:` field name in design.md's Interfaces/Contracts table
(`progress | content | blocked | error | done`) so a serializer never needs
an `isinstance` chain hardcoded to string literals in two places.

Exactly one terminal event (`blocked | error | done`) closes a turn's event
stream; `progress`/`content` are zero-or-more and never terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Union


@dataclass(frozen=True)
class ProgressEvent:
    """A running tool, named only by its static label (spec: "Progress
    Events During Tool Execution" — never args or results)."""

    label: str
    type: ClassVar[str] = "progress"


@dataclass(frozen=True)
class ContentEvent:
    """A chunk of model text that has already passed `inspect_output` for
    the complete `AIMessage` it belongs to (spec: "No Unguarded Content
    Reaches the Client")."""

    text: str
    type: ClassVar[str] = "content"


@dataclass(frozen=True)
class BlockedEvent:
    """Terminal: the guardrail blocked input or output. `replace=True`
    always — the client MUST discard any prior `content` events for this
    turn (spec: "Blocked-Turn Replace Semantics")."""

    message: str
    replace: bool = True
    type: ClassVar[str] = "blocked"


@dataclass(frozen=True)
class ErrorEvent:
    """Terminal: a provider or graph-layer failure surfaced after SSE
    headers were already committed (spec: "Failure Handling and
    Checkpointer Safety" — the post-first-byte window). `code` is one of
    `provider_unavailable | agent_error`, matching
    `app.api.errors.ProviderUnavailableError` / `AgentExecutionError`.
    `message` is always the generic, client-safe text — never provider
    internals or a stack trace."""

    code: str
    message: str
    replace: bool = True
    type: ClassVar[str] = "error"


@dataclass(frozen=True)
class DoneEvent:
    """Terminal: the turn completed normally. Carries the PUBLIC
    `thread_id` (never the internal `{thread_id}#{generation}` the
    `ThreadRegistry` uses for the checkpointer)."""

    thread_id: str
    status: str = "ok"
    type: ClassVar[str] = "done"


AgentEvent = Union[ProgressEvent, ContentEvent, BlockedEvent, ErrorEvent, DoneEvent]
