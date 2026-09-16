"""Pure guardrail core: `inspect_input` / `inspect_output` -> `GuardrailDecision`.

No LangChain import here (design.md Decision 6 / the file-split rationale
in this change's design): this module must be unit-testable with no LLM, no
agent, and no `langchain` installed. `app/security/middleware.py` (a later
PR) is the only module allowed to bridge this core to `create_agent`.

Verdicts are binary (`ALLOW`/`BLOCK`, deny-by-default) per spec — no partial
redaction, no warning tier. Both public functions never raise: any
unexpected internal failure is caught and reported as a fail-closed
`GUARDRAIL_ERROR` BLOCK, matching `resolve_role`'s fail-closed convention
(F-B1/F-B2 "the core never raises" rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.security.injection import MAX_SCAN_CHARS, find_injection
from app.security.roles import RESTRICTED_FIELDS, Role, find_restricted_fields, resolve_role

_SAFE_MESSAGE = "I cannot assist with that request."

_MAX_TOOL_ARG_DEPTH = 5


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ToolCall:
    """A model-proposed tool call, framework-free (design.md: the adapter
    maps `AIMessage`/LangChain tool-call dicts to this; the core never sees
    LangChain types)."""

    name: str
    args: dict


@dataclass(frozen=True)
class AgentOutput:
    """The model's turn, framework-free: final text plus any proposed tool
    calls, both inspected before either reaches the user or a tool."""

    text: str
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GuardrailDecision:
    """Verdict for one `inspect_input`/`inspect_output` call.

    `reason_code` is one of: OK | INJECTION_PATTERN | RESTRICTED_FIELD_REQUEST
    | RESTRICTED_FIELD_IN_OUTPUT | RESTRICTED_FIELD_IN_TOOL_ARGS | GUARDRAIL_ERROR.
    `matched` carries pattern IDs or canonical field names — for logs only,
    NEVER surfaced to the caller (that's what `message` is for: static,
    generic, reveals nothing about what triggered the block).
    """

    verdict: Verdict
    reason_code: str
    matched: tuple[str, ...]
    message: str


def _fields_above_role(text: str, role: Role) -> tuple[str, ...]:
    """Canonical restricted fields named in `text` that `role` may NOT see."""
    found = find_restricted_fields(text)
    return tuple(f for f in found if RESTRICTED_FIELDS[f] > role)


def _flatten_to_strings(value: object, depth: int = 0) -> list[str]:
    """Recursively flatten tool-call args (keys and values) into strings.

    Depth-capped at `_MAX_TOOL_ARG_DEPTH` (design.md: "recursively
    flattened, depth-capped at 5") so a pathological/deeply nested payload
    can't blow the stack or the scan cost.
    """
    if depth > _MAX_TOOL_ARG_DEPTH:
        return []

    if isinstance(value, dict):
        collected: list[str] = []
        for key, sub_value in value.items():
            collected.append(str(key))
            collected.extend(_flatten_to_strings(sub_value, depth + 1))
        return collected

    if isinstance(value, (list, tuple, set)):
        collected = []
        for item in value:
            collected.extend(_flatten_to_strings(item, depth + 1))
        return collected

    return [str(value)]


def inspect_input(text: str, role: object) -> GuardrailDecision:
    """Inspect the user's turn BEFORE the model runs.

    BLOCK if an injection pattern matches (`INJECTION_PATTERN`) OR a
    restricted field is named that `role` may not see
    (`RESTRICTED_FIELD_REQUEST`). Injection is checked first: an
    instruction-override attempt is the higher-priority signal even if it
    happens to also name a field. `role` is resolved via `resolve_role`
    (fail-closed) before any comparison.
    """
    try:
        safe_text = text if isinstance(text, str) else str(text or "")
        effective_role = resolve_role(role)

        matched_patterns = find_injection(safe_text)
        if matched_patterns:
            return GuardrailDecision(
                verdict=Verdict.BLOCK,
                reason_code="INJECTION_PATTERN",
                matched=matched_patterns,
                message=_SAFE_MESSAGE,
            )

        matched_fields = _fields_above_role(safe_text[:MAX_SCAN_CHARS], effective_role)
        if matched_fields:
            return GuardrailDecision(
                verdict=Verdict.BLOCK,
                reason_code="RESTRICTED_FIELD_REQUEST",
                matched=matched_fields,
                message=_SAFE_MESSAGE,
            )

        return GuardrailDecision(verdict=Verdict.ALLOW, reason_code="OK", matched=(), message="")
    except Exception:
        return GuardrailDecision(
            verdict=Verdict.BLOCK,
            reason_code="GUARDRAIL_ERROR",
            matched=(),
            message=_SAFE_MESSAGE,
        )


def inspect_output(payload: AgentOutput, role: object) -> GuardrailDecision:
    """Inspect the model's final text AND its proposed tool-call arguments.

    BLOCK if a restricted field above `role` appears in the final text
    (`RESTRICTED_FIELD_IN_OUTPUT`) or in any tool-call argument, keys and
    values, recursively flattened (`RESTRICTED_FIELD_IN_TOOL_ARGS`,
    threat T4: catches data written *into* the ERP via tool args before the
    tool runs). Text is checked first, independent of whether any tool
    actually returned the field (spec: "even if no tool call in this turn
    returned" it).
    """
    try:
        effective_role = resolve_role(role)

        raw_text = payload.text if isinstance(payload.text, str) else str(payload.text or "")
        text_matches = _fields_above_role(raw_text[:MAX_SCAN_CHARS], effective_role)
        if text_matches:
            return GuardrailDecision(
                verdict=Verdict.BLOCK,
                reason_code="RESTRICTED_FIELD_IN_OUTPUT",
                matched=text_matches,
                message=_SAFE_MESSAGE,
            )

        tool_matches: set[str] = set()
        for tool_call in payload.tool_calls:
            flattened = _flatten_to_strings(tool_call.args)
            combined = " ".join(flattened)[:MAX_SCAN_CHARS]
            tool_matches.update(_fields_above_role(combined, effective_role))

        if tool_matches:
            return GuardrailDecision(
                verdict=Verdict.BLOCK,
                reason_code="RESTRICTED_FIELD_IN_TOOL_ARGS",
                matched=tuple(sorted(tool_matches)),
                message=_SAFE_MESSAGE,
            )

        return GuardrailDecision(verdict=Verdict.ALLOW, reason_code="OK", matched=(), message="")
    except Exception:
        return GuardrailDecision(
            verdict=Verdict.BLOCK,
            reason_code="GUARDRAIL_ERROR",
            matched=(),
            message=_SAFE_MESSAGE,
        )
