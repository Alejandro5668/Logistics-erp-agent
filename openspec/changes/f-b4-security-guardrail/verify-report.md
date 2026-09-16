# Verify Report: F-B4 Security Guardrail - PR 1 (core guardrail)

Scope note: This verification covers PR 1 only - Phases 1-3 (roles.py,
injection.py, guardrail.py) + tests 5.1-5.3, on branch
feature/f-b4-security-guardrail. Phase 4 (middleware.py), its export in
__init__.py, and test 5.4 (test_security_middleware.py) are explicitly
deferred to PR 2 (feature/f-b4-security-guardrail-middleware, branched from
main after PR 1 merges) per tasks.md Work Unit Rationale. Their absence
in this branch is NOT a gap for this verify pass; PR 2 will get its own
independent verify.

Verdict: PASS

## Completeness (PR 1 scope)

| Task | Status | Evidence |
|---|---|---|
| 1.1 app/security/__init__.py | done | Exports Role, resolve_role, inspect_input, inspect_output only; build_security_middleware correctly NOT exported |
| 1.2 app/security/roles.py | done | Role(IntEnum), RESTRICTED_FIELDS, FIELD_ALIASES, _normalize_field, resolve_role all present |
| 2.1 app/security/injection.py | done | INJECTION_PATTERNS (16 entries = 8 IDs x EN/ES), find_injection, MAX_SCAN_CHARS truncation |
| 3.1-3.3 app/security/guardrail.py | done | Verdict, ToolCall, AgentOutput, GuardrailDecision, inspect_input, inspect_output |
| 5.1 tests/test_security_roles.py | done | 47 tests, all passing |
| 5.2 tests/test_security_injection.py | done | 36 tests, all passing |
| 5.3 tests/test_security_guardrail.py | done | 57 tests, all passing, incl. load-bearing output backstop |
| 4.1 app/security/middleware.py | deferred (PR 2) | Out of scope - correctly not present |
| 5.4 tests/test_security_middleware.py | deferred (PR 2) | Out of scope - correctly not present |
| 6.1/6.2 __init__.py full exports | partial, as designed | build_security_middleware deferred to PR 2, matches tasks.md note |

No unchecked PR-1-scope task found. Task checkboxes accurately reflect code state.

## Test Execution

Command: python -m pytest -v (full suite, repo root)

Result: 209 passed, 0 failed, 704 warnings (all pre-existing chromadb/pydantic deprecation
warnings from test_rag_search.py, unrelated to this change), 8.58s.

Breakdown (matches apply's report exactly):
- tests/test_security_roles.py: 47 passed
- tests/test_security_injection.py: 36 passed
- tests/test_security_guardrail.py: 57 passed
- Pre-existing F-B1/F-B2/F-B3 suite: 69 passed (209 minus 140 = 69)

## Spec Compliance Matrix

| Requirement | Scenario | Verdict | Covering Test |
|---|---|---|---|
| Callable Guardrail Interface | ALLOW for benign call | PASS | TestInspectInputAllowsBenignQueries |
| Callable Guardrail Interface | BLOCK with reason+safe message | PASS | TestInspectInputInjectionBlocks, TestMessageHygiene |
| Input-Side Injection Detection | Injection blocks pre-model | PASS | test_injection_pattern_blocks_before_field_check_with_reason_code |
| Input-Side Injection Detection | Legitimate query not blocked | PASS | TestMustNotBlockCorpus (input direction) |
| Output-Side Restricted-Field Detection | Field in tool-call arg -> BLOCK | PASS | TestInspectOutputToolCallArgs |
| Output-Side Restricted-Field Detection | Field in final text only -> BLOCK | PASS | TestInspectOutputBackstop.test_output_blocks_even_when_no_tool_ever_returned_the_field |
| Role-Based Field Visibility | FINANCE_MANAGER allowed where EMPLOYEE blocked | PASS | TestFinanceManagerAndAdminVisibility |
| Role-Based Field Visibility | ADMIN allowed same restricted fields | PASS | test_admin_allowed_national_id, test_finance_manager_blocked_for_national_id_admin_only_field (proves two tiers, not one flag) |
| Fail-Closed Default | Missing/unknown role -> least privilege | PASS | TestFailClosedRoleInGuardrail, TestResolveRoleFailClosed |
| Known Limitation (role spoofable) | Guardrail trusts supplied role | PASS behavior / WARNING doc surface | Behavior implicit in every role-based test; see Issues below for doc-surface gap |

WARNING - spec/design terminology drift (non-blocking): spec.md's injection scenario (line 45)
pins the literal reason string prompt_injection_detected, while design.md's Interfaces/Contracts
section and the actual implementation use INJECTION_PATTERN (app/security/guardrail.py, confirmed
by all passing tests). No test asserts the spec's literal string; the functional requirement
(non-empty reason code) is satisfied either way. Recommend reconciling spec.md wording to
design.md's authoritative enum for future readers.

## Targeted Attention Items (per verify request)

1. Output backstop test (load-bearing, defense-in-depth proof) - CONFIRMED NOT TRIVIAL.
TestInspectOutputBackstop.test_output_blocks_leak_even_when_input_passed_cleanly
(tests/test_security_guardrail.py:71-85) explicitly asserts the precondition
input_decision.verdict == Verdict.ALLOW on a benign-looking input string BEFORE checking that
inspect_output independently BLOCKs on "salario" in the model's answer text. The test's own
docstring states it is intentionally impossible to pass by relying on input-side detection
alone. This genuinely proves defense-in-depth, not just co-located assertions.

2. resolve_role whitespace bug fix - CONFIRMED CORRECT.
app/security/roles.py:158-166: string matching is raw.upper() with no .strip(), so
"ADMIN " (trailing space) fails the "in Role.__members__" membership check and falls through to
Role.EMPLOYEE, fail-closed as required. Inline comment explicitly documents the decision
(case-insensitive but NOT whitespace-tolerant). Regression test
test_unknown_or_malformed_resolves_to_employee_no_exception[ADMIN ] in
tests/test_security_roles.py (parametrize list includes "ADMIN " at line 105) - PASSED.

3. Fail-closed behavior across the board - CONFIRMED, all six cases pass with no exception:
resolve_role(None), resolve_role(""), resolve_role("root"), resolve_role(123),
resolve_role(object()) all covered by TestResolveRoleFailClosed's parametrize list
(tests/test_security_roles.py:104-108) -> all Role.EMPLOYEE.
resolve_role(True) / resolve_role(False) covered separately by
test_bool_does_not_coerce_via_int (tests/test_security_roles.py:110-114) - code explicitly
special-cases isinstance(raw, bool) BEFORE the isinstance(raw, int) branch
(app/security/roles.py:168-172) so bool's int-subclass relationship cannot silently coerce
True to a privileged role. All PASSED.

4. Message hygiene - CONFIRMED. GuardrailDecision.message is always the module-level
constant _SAFE_MESSAGE = "I cannot assist with that request." (app/security/guardrail.py:23)
- never string-interpolated with matched data at any call site in inspect_input/
inspect_output. This is a stronger guarantee than test-only coverage: the message literally
cannot carry dynamic content by construction. TestMessageHygiene
(tests/test_security_guardrail.py:254-276) additionally asserts no field name, no pattern ID,
and that the message is identical/static across trigger types - all PASSED. matched/
reason_code correctly carry the diagnostic detail for logs, per design.

5. Catalog anti-drift lock - CONFIRMED EXACT.
TestRestrictedFieldsAntiDrift.test_exact_key_set locks
{salary, bank_account, employee_id, national_id, personal_contact} and
test_exact_minimum_roles locks salary/bank_account/employee_id -> FINANCE_MANAGER,
national_id/personal_contact -> ADMIN (tests/test_security_roles.py:42-56) - matches
design.md's Interfaces/Contracts catalog verbatim. Both PASSED.

6. No langchain import in PR 1 scope - CONFIRMED. Searched
app/security/*.py, app/security/__init__.py, and all three PR-1 test files for
"import langchain" / "from langchain" (not langchain_core): zero matches (the one textual hit
was the word "langchain" inside a docstring/comment in guardrail.py, not an import statement).
The only langchain_core imports in the repo are in unrelated, pre-existing files
(app/rag/store.py, app/tools/erp_data.py, app/tools/tax_discrepancy.py) from F-B1-B3, out of
this change's scope. app/security/middleware.py (the only module design.md permits to import
langchain) does not exist yet in this branch, consistent with PR 2 deferral.

## Issues

CRITICAL: None.

WARNING:
1. spec.md scenario reason-code string (prompt_injection_detected) does not match
   design.md/implementation's INJECTION_PATTERN - doc-only drift, no test depends on the
   spec's literal string, functional requirement is satisfied. Recommend syncing spec.md
   wording before archive.
2. The "Known Limitation - Client-Supplied Role Is Spoofable" (R1) requirement's documentation
   directive is fulfilled in design.md's Threat Model and tasks.md's Notes, but not yet
   surfaced in the top-level README.md (grepped for security/guardrail/role - no matches).
   Given PR 1 is core-logic-only (nothing wires this into a running agent yet), deferring the
   README update to when PR 2 completes end-to-end integration is reasonable, but flagging so it
   is not silently dropped by the time the full feature ships.

SUGGESTION: None beyond the two WARNINGs above.

## Design Coherence

All PR-1-scope design decisions honored: pure core / thin adapter split (no LangChain import
below middleware.py), IntEnum role ladder with role >= required comparison, catalog +
alias-map DRY shape, explicit compiled regex list (no ML/NLP), MAX_SCAN_CHARS ReDoS guard,
static safe message, fail-closed resolve_role, framework-free AgentOutput/ToolCall core
types. No deviations found.

## Final Verdict

PASS for PR 1 scope (Phases 1-3 + tests 5.1-5.3). 209/209 tests passing, all six targeted
attention items independently confirmed at both the test-evidence and source-code level. Two
non-blocking WARNINGs recorded (spec/design terminology drift; README doc-surface gap) - neither
blocks archive of this PR. Recommend sdd-archive for PR 1; PR 2 (middleware) requires its own
apply + verify cycle.
