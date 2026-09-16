# Verify Report: F-B4 Security Guardrail - PR 2 (middleware adapter)

Scope note: This verification covers PR 2 only - Phase 4 (app/security/middleware.py),
test 5.4 (tests/test_security_middleware.py), the completed app/security/__init__.py
export list (adds build_security_middleware), and requirements.txt (adds langchain>=0.3),
on branch feature/f-b4-security-guardrail-middleware. PR 1's roles.py/injection.py/
guardrail.py core and tests 5.1-5.3 already merged and verified separately
(openspec/changes/f-b4-security-guardrail/verify-report.md, PASS) and are re-run here
only as regression evidence, not re-judged for correctness.

Verdict: PASS

## Completeness (PR 2 scope)

| Task | Status | Evidence |
|---|---|---|
| 4.1 app/security/middleware.py | done | build_security_middleware() factory, SecurityGuardrailMiddleware(AgentMiddleware) with before_model/after_model, _role_from_context, _message_text, _to_agent_output, _block_update all present |
| 5.4 tests/test_security_middleware.py | done | 19 tests, all passing |
| 6.1 app/security/__init__.py (full exports) | done | Now exports Role, resolve_role, inspect_input, inspect_output, build_security_middleware - all five present |
| 6.2 module import paths | done | from app.security import build_security_middleware verified working via passing test suite and manual import checks below |
| requirements.txt | done | langchain>=0.3 added; installed version confirmed 1.4.0 |

No unchecked PR-2-scope task found. Task checkboxes in tasks.md accurately reflect code state.

## Test Execution

Command: python -m pytest -v (full suite, repo root)

Result: 228 passed, 0 failed, 704 warnings (pre-existing chromadb/pydantic deprecation
warnings from test_rag_search.py, unrelated to this change), 9.38s.

Breakdown:
- tests/test_security_middleware.py: 19 passed (new, PR 2)
- tests/test_security_roles.py + test_security_injection.py + test_security_guardrail.py: 140 passed (PR 1 core, regression-confirmed unchanged)
- Pre-existing F-B1/F-B2/F-B3 suite: 69 passed
- Total: 19 + 140 + 69 = 228, matches the 209 pre-existing (140 + 69) + 19 new claim exactly.

## Spec Compliance Matrix (PR 2 relevant requirements)

| Requirement | Scenario | Verdict | Covering Test |
|---|---|---|---|
| Input-Side Prompt-Injection Detection | Injection blocks before model runs, adapter wiring | PASS | TestBeforeModelHookShape::test_injection_blocks_with_jump_to_end_and_safe_message |
| Input-Side Prompt-Injection Detection | Legitimate query not blocked, adapter wiring | PASS | TestBeforeModelHookShape::test_callable_and_returns_none_on_allow |
| Output-Side Restricted-Field Detection | Field in tool-call args -> BLOCK before tool executes | PASS | TestAfterModelHookShape::test_restricted_field_in_tool_call_args_blocks_before_tool_executes |
| Output-Side Restricted-Field Detection | Field in final text only -> BLOCK | PASS | TestAfterModelHookShape::test_restricted_field_in_text_blocks_with_jump_to_end |
| Role-Based Field Visibility | FINANCE_MANAGER allowed where EMPLOYEE blocked, at the hook | PASS | test_restricted_field_request_allowed_for_finance_manager + test_restricted_field_allowed_for_authorized_role |
| Fail-Closed Default | Missing/malformed role at the adapter boundary | PASS | test_default_resolver_fails_closed_on_missing_context, test_custom_resolver_can_fail_closed_too |
| Known Limitation (role spoofable) | Adapter trusts resolver output, no auth | PASS behavior, unchanged from PR 1 | Implicit in every role-based adapter test |

## Targeted Attention Items (per verify request)

1. API-shape drift vs design.md - CONFIRMED FAITHFUL TO INTENT, syntax differs as documented.
Inspected the installed langchain==1.4.0 API directly:
inspect.signature(AgentMiddleware.before_model) returns
(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None, matching
middleware.py class-based before_model(self, state: AgentState, runtime: Runtime) and
after_model(self, state, runtime) exactly. hook_config(can_jump_to=...) is confirmed to exist
and to be required to unlock the jump_to key (its docstring says to use this decorator on
before_model or after_model methods to configure which destinations they can jump to).
All three of design.md INTENT anchors hold:
  - One middleware object: build_security_middleware() returns a single
    SecurityGuardrailMiddleware() instance (middleware.py line 171), not two exports.
  - jump_to=end is the exact blocking-update key the installed API expects - the design.md
    Data Flow diagram assumption was correct even though the flat before_model(context: dict)
    sketch was not.
  - Role is resolved per-turn, not bound at build time (see item 5 below).
The docstring at the top of middleware.py (lines 10-20) explicitly documents this drift and
attributes it to the same re-confirmation practice used for the F-B3 chromadb precedent. This
is a faithful, well-documented adaptation, not an undisclosed deviation.

2. Single-object factory (threat T6) - CONFIRMED.
build_security_middleware() (middleware.py:113-171) defines SecurityGuardrailMiddleware as a
local class and returns exactly one instance of it: return SecurityGuardrailMiddleware(). Both
before_model and after_model are instance methods of that one class - a caller cannot obtain
one hook without the other. Verified at runtime:
TestFactoryReturnsOneObject::test_factory_returns_single_agent_middleware_instance (isinstance
check against AgentMiddleware) and test_returned_object_carries_both_hooks_no_loose_helpers
(both hooks callable on the same object) both PASSED. app/security/__init__.py exports only
the factory function, never the class or the hook methods directly, so nothing in the public
surface invites half-wiring.

3. Fail-closed at the adapter layer - CONFIRMED via source inspection AND live probing beyond
the shipped test suite.
Both before_model and after_model wrap role_resolver(...), message-text extraction, and
inspect_input/inspect_output invocation in a bare try/except Exception: return
_block_update(_ADAPTER_SAFE_MESSAGE) (middleware.py:137-146, 156-165). Independently verified
this catches unanticipated failures the shipped tests do not exercise, by injecting:
  - a role_resolver that raises ValueError -> both hooks returned jump_to: end plus the
    generic safe message (BLOCK), not a crash and not a silent ALLOW.
  - a state-like object whose .get() raises RuntimeError -> same BLOCK result.
  - a message with tool_calls set to a non-iterable int -> same BLOCK result.
  - a message with tool_calls as a malformed dict (missing args key) or as a bare string ->
    no crash; malformed-but-iterable shapes degrade to ALLOW only because they produce no
    restricted-field match, never because the exception path silently passed through.
This is stricter than the shipped test file requires and confirms fail-closed extends past the
pure core into the adapter boundary, as design.md Failure Mode decision requires (adapter
exception -> BLOCK).

4. Zero LangChain leakage into the pure core - CONFIRMED, PR 2 changes included.
Grepped app/security/roles.py, app/security/injection.py, and app/security/guardrail.py for
langchain: zero import statements in any of the three (one textual match in guardrail.py is
a docstring comment explaining the core stays framework-free, not an import). middleware.py
remains the only module importing langchain/langchain_core. This holds even after
langchain>=0.3 was promoted from being F-B5 responsibility to a real, installed PR-2
dependency - the core files were not touched by that change.

5. Per-invocation role resolution - CONFIRMED.
role_resolver is stored as a build_security_middleware parameter (closed over by the local
class) but is called inside the body of before_model and after_model on every invocation -
role = role_resolver(runtime.context) appears inside both hook methods (middleware.py:142,
161), not in build_security_middleware own body. This means one middleware instance built
once can serve callers with different runtime.context["role"] values turn-by-turn.
TestCustomRoleResolverInjection::test_default_resolver_reads_role_from_dict_context proves
this directly: the same state is passed through before_model twice with
Runtime(context={"role": "ADMIN"}) then Runtime(context={"role": "EMPLOYEE"}) on the same
middleware object, producing allowed is None then blocked is not None - different verdicts
from the same instance, same input text, different per-call role. PASSED.

6. _to_agent_output tool-call mapping - CONFIRMED correct for the real shape, and does not
crash on malformed/missing tool_calls.
For LangChain actual AIMessage.tool_calls shape ({"name": str, "args": dict, "id": str,
"type": "tool_call"}), _to_agent_output (middleware.py:82-99) correctly extracts name via
tc.get("name", "") and args via tc.get("args") or {} - verified end-to-end by
test_restricted_field_in_tool_call_args_blocks_before_tool_executes and
test_clean_output_with_tool_calls_allowed, both PASSED, using real tool-call dicts.
Independent manual probing (beyond the shipped suite) with malformed shapes - missing args
key, tool_calls as a bare string, tool_calls as a non-iterable int - confirmed no crash in any
case: the first two degrade gracefully to ALLOW (no restricted content found), and the
non-iterable case is caught by the hook own try/except and correctly resolves to BLOCK (see
item 3).

## Issues

CRITICAL: None.

WARNING:
1. Carried forward from PR 1 verify-report.md: the "Known Limitation - Client-Supplied Role
   Is Spoofable" (R1) documentation directive is satisfied in spec.md and design.md Threat
   Model, but still not surfaced in the top-level README.md (grepped for
   security/guardrail/role/spoofable - no matches). PR 2 scope is the middleware adapter only
   and does not touch README.md, so this gap is still open at the end of the F-B4 change as a
   whole. Recommend adding a short README note before or during archive, since F-B4 is now
   functionally wired end-to-end (adapter exists) and no later PR in this change owns README.
2. design.md Architecture Decisions table (Dependency row) still reads "No new requirement;
   langchain is F-B5 to add... Pin langchain now [rejected]" - this is now stale relative to
   the actual PR 2 delivery, which does pin langchain>=0.3 in requirements.txt and documents
   the reversal clearly in tasks.md (Phase 4 note) and in middleware.py / the test file
   docstrings. The decision itself is well-justified and consistently applied in code, tasks.md,
   and the test file - only the design.md decision table row was not updated to match. Doc-only
   drift, non-blocking, similar in nature to PR 1 spec/design reason-code wording drift.

SUGGESTION: None beyond the two WARNINGs above.

## Design Coherence

All PR-2-scope design decisions honored:
- Adapter is the only module importing langchain (confirmed, item 4 above).
- jump_to=end blocking-update key matches design.md Data Flow diagram exactly, despite the
  class-based AgentMiddleware shape replacing the flat-dict sketch (item 1 above) - this is the
  Open Question design.md explicitly flagged for re-confirmation at apply time, and it was
  re-confirmed and documented rather than silently guessed.
- role_resolver injected into the factory, defaulting to reading context["role"] /
  getattr(..., "role", None), called per-turn not bound at build time (design.md "Role at the
  hook" decision; item 5 above).
- Output payload mapping keeps langchain_core.messages / tool-call dict shapes entirely inside
  the adapter; the pure core only ever sees AgentOutput/ToolCall (design.md "Output payload"
  decision).
- Factory returns one object carrying both hooks (design.md threat T6; item 2 above).
- Adapter-side exception handling fails closed to BLOCK with the same generic safe message
  convention as the pure core (design.md "Failure Mode" decision; item 3 above).

No deviations found beyond the two documentation-only WARNINGs above (neither affects code
behavior or test coverage).

## Final Verdict

PASS for PR 2 scope (Phase 4 + test 5.4 + __init__.py export completion +
requirements.txt). 228/228 tests passing across the full suite (209 pre-existing + 19 new
middleware tests, exactly matching the expected count). All six targeted attention items
independently confirmed at both the test-evidence level and via direct source/runtime
inspection beyond the shipped test suite (items 1, 3, and 6 in particular were cross-checked
against the live installed langchain==1.4.0 API and with manually injected failure modes not
covered by the existing tests). Two non-blocking WARNINGs recorded (README doc-surface gap for
R1, now that F-B4 is fully wired; stale design.md Dependency decision-table row). Neither
blocks archive. Recommend sdd-archive for the F-B4 change as a whole (both PRs now verified
independently, both PASS).
