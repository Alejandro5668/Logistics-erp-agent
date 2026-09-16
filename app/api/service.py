"""The guarded sink: `run_turn()` (design.md "Empirical verification" + all
five Architecture Decisions).

This is the ONE place F-B6 owns real logic — everything else in `app/api/`
is glue. `run_turn()` drives `agent.astream(..., stream_mode="updates")`
(never `"messages"`: token-level streaming fires before the guardrail's
`after_model` hook exists as a node — E2, empirically confirmed) and
re-applies `inspect_output` to every complete `AIMessage` itself, before any
text is ever yielded as an `AgentEvent`. `ToolMessage`s are dropped
entirely; only static `TOOL_LABELS`-mapped progress events derived from
approved tool-call *names* are emitted (never args or results, R5).

Empirically verified against the installed `langchain==1.4.0`,
`langgraph==1.2.11` (via a scripted-model probe run through `build_agent`,
mirroring design.md's own verification method — no shell available at
package-inspection time, so this was live execution, not source reading):

- A node named `"model"` yields `{"messages": [<raw AIMessage>]}` BEFORE the
  security middleware's own `"{Middleware}.after_model"` node runs. This is
  E2 made concrete: the raw, unvetted `AIMessage` is visible to a stream
  consumer at the `"model"` node's update, one superstep before the
  guardrail's node exists. The sink treats this raw message as ALLOW-or-BLOCK
  itself, via its OWN `inspect_output` call — it never trusts `"model"`'s
  update as pre-approved.
- A guardrail BLOCK (either hook) always returns
  `{"messages": [<safe AIMessage>], "jump_to": "end"}`. This key pair is the
  ONLY node-name-agnostic signal a block occurred (design.md "no node-name
  coupling") — the sink watches for `jump_to == "end"` on ANY node's update,
  never a hardcoded node name (the class name `SecurityGuardrailMiddleware`
  is an implementation detail of `app/security/middleware.py`, not a public
  contract).
- A `"tools"` node yields `{"messages": [<ToolMessage>, ...]}` — dropped
  unconditionally, whatever its `status`.

Because `inspect_output` is pure and deterministic (design.md's rationale),
a sink-computed BLOCK on the raw `"model"` update and the middleware's own,
later, independently-computed BLOCK on the SAME message are guaranteed to
agree. The sink does not need to wait for the middleware's own node to
confirm this — it emits the terminal `blocked` event as soon as it decides,
then keeps draining the underlying stream (without emitting anything
further) so the graph still reaches its own `jump_to: "end"` and closes the
checkpoint cleanly. Stopping early instead would leave the checkpoint at an
incomplete superstep (the raw `AIMessage` written, but the middleware's own
`after_model` node never run) — the same poisoned shape `ThreadRegistry`
exists to prevent. A guardrail BLOCK is therefore never treated as a
"failure": `ThreadRegistry.bump()` is reserved for genuine exceptions.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, ToolMessage

from app.api.dependencies import ThreadRegistry
from app.api.errors import AgentExecutionError, ProviderUnavailableError
from app.api.events import AgentEvent, BlockedEvent, ContentEvent, DoneEvent, ProgressEvent
from app.api.schemas import ChatRequest
from app.security import inspect_output
from app.security.guardrail import AgentOutput, ToolCall, Verdict

# Static name -> label map (design.md "Decision: Progress from approved
# tool-call names"). Keys are the 5 tools `app.agent.AGENT_TOOLS` wires;
# an unrecognized name (future tool, or a scripted-model typo in tests)
# falls back to the generic label rather than ever echoing the raw name
# verbatim to the wire — the label set is the contract, not the tool list.
TOOL_LABELS: dict[str, str] = {
    "get_erp_data": "Looking up ERP order data...",
    "calculate_tax_discrepancy": "Calculating tax discrepancy...",
    "search_regulations": "Searching regulations...",
    "create_erp_adjustment": "Applying ERP adjustment...",
    "notify_human": "Escalating to a human reviewer...",
}
_DEFAULT_TOOL_LABEL = "Running a tool..."

# Exception classification heuristic (no provider SDK is an installed
# dependency of this repo — see requirements.txt — so there is no concrete
# provider exception type to `isinstance`-check against). Built-in
# connectivity/timeout types plus a small keyword scan over the exception's
# class name and message classify "provider failed" vs. "everything else is
# a graph/tool-node error" (spec: "Failure Handling and Checkpointer
# Safety"). This is a pragmatic prototype-level heuristic, not a provider
# integration; it is unit-tested directly against synthetic exceptions.
_PROVIDER_ERROR_TYPES: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError, OSError)
_PROVIDER_KEYWORDS = (
    "timeout",
    "timed out",
    "rate limit",
    "ratelimit",
    "too many requests",
    "unauthorized",
    "authentication",
    "api key",
    "connection",
    "network",
)


def tool_label(name: str) -> str:
    """Map an approved tool-call name to its static progress label."""
    return TOOL_LABELS.get(name, _DEFAULT_TOOL_LABEL)


def _message_text(message: object) -> str:
    """Extract plain text from a LangChain message's `content`.

    Mirrors `app.security.middleware._message_text` exactly (`content` is
    usually `str`, but the content-blocks API allows a list of blocks).
    Duplicated rather than imported: this module owns the HTTP-layer sink
    and must not reach into `app.security.middleware`'s private helpers
    (design.md's layering — the adapter owns zero HTTP-layer concerns, and
    this module owns zero LangChain-middleware-hook concerns). Never
    raises: any unexpected shape coerces to `str(...)`.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts)
    return str(content) if content is not None else ""


def _to_agent_output(ai_message: object) -> AgentOutput:
    """Map a LangChain `AIMessage` to the framework-free `AgentOutput` the
    pure `inspect_output` core accepts. Mirrors
    `app.security.middleware._to_agent_output` (same duplication rationale
    as `_message_text` above): the sink re-applies the SAME pure guardrail
    logic the middleware will separately, redundantly apply, and both must
    build the identical `AgentOutput` shape for the determinism argument in
    this module's docstring to hold.
    """
    text = _message_text(ai_message)
    raw_tool_calls = getattr(ai_message, "tool_calls", None) or []
    tool_calls = tuple(
        ToolCall(
            name=tc.get("name", "") if isinstance(tc, dict) else str(getattr(tc, "name", "")),
            args=(tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)) or {},
        )
        for tc in raw_tool_calls
    )
    return AgentOutput(text=text, tool_calls=tool_calls)


def _last_message_text(node_value: dict) -> str:
    """Extract the text of the last message in a node's `updates` value —
    used only for the `jump_to: "end"` branch, where the middleware has
    already decided BLOCK and the safe message is the update's own payload
    (`app.security.middleware._block_update`); no `inspect_output` re-check
    needed or possible (the message IS the safe text already)."""
    messages = node_value.get("messages") or []
    if not messages:
        return ""
    return _message_text(messages[-1])


def _classify_exception(exc: Exception) -> ProviderUnavailableError | AgentExecutionError:
    """Classify a surviving exception into the one of two typed,
    client-safe exceptions `app/api/errors.py` defines. See module
    docstring for why this is a heuristic, not a provider-SDK `isinstance`
    check."""
    if isinstance(exc, _PROVIDER_ERROR_TYPES):
        return ProviderUnavailableError()
    signature = f"{type(exc).__name__} {exc}".lower()
    if any(keyword in signature for keyword in _PROVIDER_KEYWORDS):
        return ProviderUnavailableError()
    return AgentExecutionError()


async def run_turn(
    request: ChatRequest,
    agent: Any,
    registry: ThreadRegistry,
) -> AsyncIterator[AgentEvent]:
    """Drive one turn of `agent` and yield framework-free `AgentEvent`s.

    `agent` is whatever `app.api.dependencies.get_agent()` (or a test
    double / `ScriptedChatModel`-backed `build_agent()`) provides — this
    function never imports `app.agent` or calls `build_agent()` itself
    (design.md "one thin HTTP adapter", no composition-root duplication).

    Raises `ProviderUnavailableError` / `AgentExecutionError` (never a bare
    exception) for any failure that survives the guarded loop; the router
    (PR 2) decides HTTP status vs. terminal SSE `error` event based on
    whether any event was already yielded (design.md "Decision: Two error
    windows"). A guardrail BLOCK is NOT an exception path — see module
    docstring.
    """
    role = request.role
    internal_thread_id = registry.get_internal_thread_id(request.thread_id)
    config = {"configurable": {"thread_id": internal_thread_id}}
    context = {"role": role}

    blocked = False
    stream = None
    try:
        stream = agent.astream(
            {"messages": [{"role": "user", "content": request.message}]},
            config=config,
            context=context,
            stream_mode="updates",
        )
        async for update in stream:
            if not isinstance(update, dict):
                continue

            for node_value in update.values():
                if not isinstance(node_value, dict):
                    continue

                if node_value.get("jump_to") == "end":
                    if not blocked:
                        blocked = True
                        yield BlockedEvent(message=_last_message_text(node_value))
                    continue

                if blocked:
                    continue  # already terminal; drain silently to let the graph close

                for message in node_value.get("messages") or []:
                    if isinstance(message, ToolMessage):
                        continue  # R5: never streamed, whatever its status
                    if not isinstance(message, AIMessage):
                        continue

                    payload = _to_agent_output(message)
                    decision = inspect_output(payload, role)
                    if decision.verdict is Verdict.BLOCK:
                        blocked = True
                        yield BlockedEvent(message=decision.message)
                        break

                    if payload.text:
                        yield ContentEvent(text=payload.text)
                    for tool_call in payload.tool_calls:
                        yield ProgressEvent(label=tool_label(tool_call.name))

        if not blocked:
            yield DoneEvent(thread_id=request.thread_id, status="ok")
    except Exception as exc:
        registry.bump(request.thread_id)
        raise _classify_exception(exc) from exc
    finally:
        if stream is not None:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()
