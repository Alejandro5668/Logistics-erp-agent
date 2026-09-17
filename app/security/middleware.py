"""LangChain adapter: bridges the pure guardrail core to `create_agent`.

The ONLY module in `app/security/` allowed to import `langchain` (design.md
Decision "domain layer has zero framework imports" / the file-split
rationale in this change's design). `roles.py`, `injection.py`, and
`guardrail.py` stay importable with no LangChain/agent installed; this
module is the thin seam that plugs the pure core into `create_agent`'s
`before_model`/`after_model` middleware hooks.

API shape note (design.md Open Questions — re-confirmed at apply time
against the installed `langchain==1.4.0`, per the F-B3 chromadb precedent):
the installed API is a class-based `AgentMiddleware` subclass with
`before_model(self, state, runtime)` / `after_model(self, state, runtime)`
methods (not the `before_model(context: dict)` flat-dict shape tasks.md
sketched). The blocking-update key IS `jump_to`, as design.md assumed:
`{"messages": [...], "jump_to": "end"}` stops the run and skips the model
(on `before_model`) or the tool node (on `after_model`). A method must be
decorated with `@hook_config(can_jump_to=["end"])` to be allowed to return
that key. The pure core contract (`roles.py`/`injection.py`/`guardrail.py`)
is unchanged by this drift; only this adapter's shape moved.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState, Runtime, hook_config
from langchain_core.messages import AIMessage

from app.security.guardrail import AgentOutput, ToolCall, Verdict, inspect_input, inspect_output

# Mirrors guardrail.py's private `_SAFE_MESSAGE` constant: used only when an
# adapter-side failure (mapping messages, calling `role_resolver`) happens
# BEFORE the pure core's own try/except can produce a `GUARDRAIL_ERROR`
# decision. Fail-closed, same generic text, never echoes internals.
_ADAPTER_SAFE_MESSAGE = "I cannot assist with that request. / No puedo ayudarte con esa solicitud."


def _role_from_context(context: Any) -> object:
    """Default `role_resolver`: read `role` off the run's context.

    `Runtime.context` can be a plain `dict` (the common case for a mock
    caller-supplied role, per design.md) or any object `create_agent`'s
    `context_schema` produces — this later becomes F-B6's seam onto a
    verified JWT claim, per design.md's DIP rationale. Never raises: an
    unreadable/absent context resolves to `None`, which `resolve_role`
    (called inside `inspect_input`/`inspect_output`) fails closed to
    `Role.EMPLOYEE`.
    """
    if context is None:
        return None
    if isinstance(context, dict):
        return context.get("role")
    return getattr(context, "role", None)


def _message_text(message: object) -> str:
    """Extract plain text from a LangChain message's `content`.

    `content` is usually a `str`, but the message-content-blocks API allows
    a list of blocks; this flattens any `text` blocks and ignores the rest
    (images, tool-result blocks, etc. carry no restricted-field text this
    guardrail is responsible for). Never raises: any unexpected shape
    coerces to `str(...)`.
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
    """Map a LangChain `AIMessage` to the framework-free `AgentOutput`.

    `AIMessage.tool_calls` is a list of dicts (`{"name", "args", "id",
    "type"}` per the installed `langchain-core`); this is the adapter's
    whole job per design.md ("the mapping is the adapter's whole job") —
    the pure core never sees an `AIMessage`.
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


def _block_update(message: str) -> dict[str, Any]:
    """The blocking state update: safe-message reply + end the run.

    `jump_to: "end"` (design.md's Data Flow diagram, confirmed against the
    installed API) skips the model entirely on `before_model` and skips the
    tool node entirely on `after_model` — the blocked turn costs zero
    tokens and reaches no tool/ERP write (threats T1/T4).
    """
    return {"messages": [AIMessage(content=message)], "jump_to": "end"}


def build_security_middleware(
    role_resolver: Callable[[Any], object] = _role_from_context,
) -> AgentMiddleware:
    """Build the one middleware object `create_agent` registers.

    Returns a single `AgentMiddleware` instance with both `before_model`
    and `after_model` hooks bound to it (design.md threat T6: one exported
    factory, no loose helpers a wiring layer could half-apply).

    `role_resolver` is called with `runtime.context` on every hook
    invocation (not bound once at build time): the agent is built once but
    serves many callers, so the role must be resolved per-turn (design.md
    "Role at the hook" decision). Swap it for a verified-claim resolver
    (F-B6) without touching this module's control flow.
    """

    class SecurityGuardrailMiddleware(AgentMiddleware):
        """Adapter middleware: `inspect_input`/`inspect_output` wired into
        `create_agent`'s `before_model`/`after_model` hooks."""

        @hook_config(can_jump_to=["end"])
        def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
            """BLOCK -> safe message + end the run; model never called.
            ALLOW -> `None` (pass through, no state update)."""
            try:
                messages = state.get("messages") or []
                if not messages:
                    return None

                role = role_resolver(runtime.context)
                text = _message_text(messages[-1])
                decision = inspect_input(text, role)
            except Exception:
                return _block_update(_ADAPTER_SAFE_MESSAGE)

            if decision.verdict is Verdict.BLOCK:
                return _block_update(decision.message)
            return None

        @hook_config(can_jump_to=["end"])
        def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
            """BLOCK -> safe message + end the run; tool never executes.
            ALLOW -> `None` (pass through, no state update)."""
            try:
                messages = state.get("messages") or []
                if not messages:
                    return None

                role = role_resolver(runtime.context)
                payload = _to_agent_output(messages[-1])
                decision = inspect_output(payload, role)
            except Exception:
                return _block_update(_ADAPTER_SAFE_MESSAGE)

            if decision.verdict is Verdict.BLOCK:
                return _block_update(decision.message)
            return None

    return SecurityGuardrailMiddleware()
