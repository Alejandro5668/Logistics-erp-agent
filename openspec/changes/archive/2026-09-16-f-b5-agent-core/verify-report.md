# Verify Report: F-B5 Agent Core - PR 1 (Phases 1-4 + tests 5.1/5.2)

Scope note: This verification covers PR 1 only - Phases 1-4 (spec/deps, actions.py +
scripted_model.py, agent/prompt.py + agent/core.py + agent/__init__.py, re-export
wiring) + tests 5.1 (test_agent_actions.py) and 5.2 (test_agent_build.py), on branch
feature/f-b5-agent-core. Test 5.3 (tests/test_agent_flow.py, L2-L4 integration) and
Phase 6 (README.md) are explicitly deferred to PR 2
(feature/f-b5-agent-core-integration, branched from main after PR 1 merges) per
tasks.md's Work Unit split. Their absence in this branch is NOT a gap for this verify
pass; PR 2 will get its own independent verify (following the F-B4 precedent of
verify-report.md + verify-report-pr2.md).

Verdict: PASS

## Completeness (PR 1 scope)

| Task | Status | Evidence |
|---|---|---|
| 1.1 spec.md amendment (delta to adjustment_amount) | done | specs/agent-core/spec.md uses adjustment_amount throughout Requirement 3 and both scenarios; remaining delta/delta_pct occurrences are F-B2's legitimate observed-deviation terminology, not the action arg name |
| 1.2 requirements.txt pins | done | langchain>=1.4,<2 (was a broken >=0.3 pin with no create_agent/AgentMiddleware), langgraph>=1.2,<2 added |
| 2.1 app/tools/actions.py | done | create_erp_adjustment, notify_human, both @tool-decorated, no SQLAlchemy import anywhere in the file, never raise |
| 2.2 tests/scripted_model.py | done | ScriptedChatModel overrides bind_tools, strict exhaustion via AssertionError, tool_call/final helpers present |
| 2.3 app/tools/__init__.py | done | Re-exports create_erp_adjustment, notify_human; search_regulations correctly NOT re-exported (stays in app.rag.store per design footnote) |
| 3.1 app/agent/prompt.py | done | SYSTEM_PROMPT constant, TOOL ORDER / DECISION POLICY / ARGUMENTS / SAFETY sections present |
| 3.2 app/agent/core.py | done | DEFAULT_MODEL, AGENT_TOOLS (5-tuple), build_agent(model=None, checkpointer=None) |
| 3.3 app/agent/__init__.py | done | Re-exports build_agent, AGENT_TOOLS, DEFAULT_MODEL |
| 4.1/4.2 import/export verification | done | All imports resolve; full suite collects and runs with no import errors |
| 5.1 tests/test_agent_actions.py | done | 25 tests, all passing |
| 5.2 tests/test_agent_build.py | done | 11 tests, all passing |
| 5.3 tests/test_agent_flow.py | deferred (PR 2) | Out of scope - correctly not present in this branch (confirmed via git diff --stat main...HEAD) |
| 6.1 README.md | deferred (PR 2) | Out of scope - correctly not present in this branch's diff |

No unchecked PR-1-scope task found. Task checkboxes in tasks.md accurately reflect
code state (5.3 and 6.1 remain unchecked, matching their deferred status).

## Test Execution

Command: python -m pytest -v (full suite, repo root, branch feature/f-b5-agent-core)

Result: 264 passed, 0 failed, 704 warnings (pre-existing chromadb/pydantic
deprecation warnings from test_rag_search.py, unrelated to this change), 4.02s.

Breakdown (matches expected 228 pre-existing + 36 new):
- tests/test_agent_actions.py: 25 passed (new)
- tests/test_agent_build.py: 11 passed (new)
- Pre-existing F-B1/F-B2/F-B3/F-B4 suite: 228 passed, unmodified (264 - 36 = 228)

git diff --stat main...HEAD confirms no pre-existing test file was touched; only
new files (app/agent/*, app/tools/actions.py, tests/scripted_model.py,
tests/test_agent_actions.py, tests/test_agent_build.py) plus modified
app/tools/__init__.py, requirements.txt, specs/agent-core/spec.md, tasks.md
appear in the diff -- zero regression risk structurally, confirmed by the passing run.

## Spec Compliance Matrix

| Requirement | Scenario | Verdict | Covering Test |
|---|---|---|---|
| Agent Factory Interface | Default construction wires 5 tools, middleware, checkpointer | PASS | TestAgentToolsConstant, TestBuildAgentWithScriptedModel (zero-arg model path is the documented offline seam per design.md Open Question 2 -- asserted via injected ScriptedChatModel, not a true zero-arg call, consistent with the design's stated limitation) |
| Model-Agnostic Model Parameter | Fake/stub BaseChatModel accepted, no network call | PASS | test_no_network_call_is_made_building_with_a_fake_model |
| Action Tools in actions.py | Adjustment returns receipt without mutating erp_orders | PASS | test_seeded_row_is_unchanged_after_call, test_rejected_call_does_not_mutate_seeded_row -- real before/after snapshot comparison via _fetch_order, not a docstring-trust assertion |
| Action Tools in actions.py | Escalation returns deterministic record, never raising | PASS | TestNotifyHumanValid, TestNotifyHumanHostileReason |
| Auto-Adjust Decision Policy | Prose policy in SYSTEM_PROMPT (+-5% AND >=1 snippet) | PASS (wiring-level; full ReAct-loop exercise deferred to PR 2 / test 5.3) | SYSTEM_PROMPT text inspected directly: DECISION POLICY section states -5 <= delta_pct <= 5 AND >=1 snippet |
| Escalation Decision Policy | Prose policy in SYSTEM_PROMPT (outside range OR empty RAG) | PASS (wiring-level; full ReAct-loop exercise deferred to PR 2 / test 5.3) | Same SYSTEM_PROMPT section, explicit escalate-when bullet list |
| Guardrail Block Ends Run | No PR-1 scope; requires full agent invoke | N/A this PR | Deferred to PR 2 test 5.3 (design.md Testing Strategy L4 Guardrail rows) |
| Thread-Scoped Session Memory | Checkpointer keyed by thread_id alone, not a singleton | PASS | test_default_checkpointer_is_used_when_none_is_passed, test_explicit_checkpointer_is_honored, test_two_independently_built_agents_get_independent_checkpointers |
| Offline Test Seam | Scripted model exercises wiring, no network | PASS | Full tests/test_agent_build.py + tests/test_agent_actions.py suite runs with zero network calls, zero credentials |

## Targeted Attention Items (per verify request)

1. requirements.txt pin fix -- CONFIRMED CORRECT AND REAL. Read requirements.txt
directly: langchain>=1.4,<2 (line 3) and langgraph>=1.2,<2 (line 4, newly
added). The Architecture Decisions table in design.md documents that the prior
>=0.3 pin resolved to versions with no create_agent/AgentMiddleware -- this was a
genuinely broken pin, not a cosmetic version bump, and the fix is present.

2. No ERP mutation -- CONFIRMED. app/tools/actions.py has zero SQLAlchemy
imports and zero references to any session/engine/write call anywhere in the
file -- it is pure dict construction with no I/O. test_seeded_row_is_unchanged_after_call
(tests/test_agent_actions.py lines 61-69) takes a real before-snapshot via
_fetch_order, invokes the tool, takes an after-snapshot, and asserts
before == after -- this is a genuine runtime assertion against the seeded SQLite
row, not a trust-the-docstring check. A parallel test
(test_rejected_call_does_not_mutate_seeded_row) covers the invalid-input path too.

3. ScriptedChatModel correctness -- CONFIRMED. bind_tools is overridden
(tests/scripted_model.py lines 39-52), records bound_tools, returns self (avoids
the base BaseChatModel.bind_tools NotImplementedError documented in the design
Verified API facts table). _generate (lines 54-71) raises
AssertionError("ScriptedChatModel exhausted -- agent took an unscripted step")
once index >= len(responses) -- strict exhaustion, not the stock fake's silent
cycling behavior the design explicitly rejected.

4. build_agent() exact create_agent() call -- CONFIRMED. app/agent/core.py
lines 69-75: system_prompt=SYSTEM_PROMPT (not prompt= or state_modifier=),
middleware=[build_security_middleware()], checkpointer=checkpointer or InMemorySaver().
Matches the design Interfaces/Contracts code block verbatim and its cited
langchain/agents/factory.py:840-856 evidence.

5. Checkpointer not a singleton -- CONFIRMED. InMemorySaver() is constructed
inside the "checkpointer or InMemorySaver()" expression at call time, i.e. fresh
per build_agent() invocation unless one is injected -- no module-level saver
exists in core.py. test_two_independently_built_agents_get_independent_checkpointers
(tests/test_agent_build.py lines 104-111) asserts agent_a.checkpointer is not
agent_b.checkpointer and PASSED.

6. SYSTEM_PROMPT legibility -- CONFIRMED. Read the actual prompt text
(app/agent/prompt.py lines 15-46): DECISION POLICY section states the auto-adjust
condition as "A. delta_pct is a number and -5 <= delta_pct <= 5" AND
"B. search_regulations returned at least one snippet for that year", with an
explicit escalate-when bullet list covering out-of-range delta, null delta_pct,
empty RAG, unknown region / invalid input, and an "anything ambiguous, escalate"
catch-all. This is legible prose, not a placeholder.

7. 228 pre-existing tests unmodified -- CONFIRMED. git diff --stat main...HEAD
shows no pre-existing test file in the changed-files list; only two new test
files (test_agent_actions.py, test_agent_build.py) plus new/modified source.
Full suite: 264/264 passing, 228 = 264 minus 36 new.

8. .func() precedent for test_non_numeric_adjustment_amount_is_rejected --
CONFIRMED CONSISTENT. tests/test_agent_actions.py lines 117-125 calls
create_erp_adjustment.func("ORD-1004", "not-a-number", "x") with an inline
comment explaining that pydantic args_schema would coerce/reject the string at
the .invoke() boundary before the function body own validation runs. This
exactly mirrors the existing pattern in tests/test_tax_discrepancy.py
(test_invalid_amount_returns_valid_input_false_no_exception,
test_invalid_reported_tax_returns_valid_input_false_no_exception,
test_no_exception_escapes_for_combined_garbage_input, all using .func() for
the same reason). Not a new inconsistent pattern -- it is the established F-B2
convention applied identically in F-B5.

## Issues

CRITICAL: None.

WARNING: None.

SUGGESTION:
1. design.md Open Questions checklist still shows all three items as unchecked
("- [ ]"), including the spec wording item stating that this design uses
adjustment_amount and that sdd-tasks must carry a one-line spec amendment or
the spec and code diverge -- which task 1.1 has in fact resolved (spec.md now
uses adjustment_amount consistently, confirmed above). This is a documentation
staleness in design.md only; it does not affect code, tests, or the spec
itself. Recommend ticking that checkbox before archive for a clean paper trail,
but it is non-blocking.

## Design Coherence

All PR-1-scope design decisions honored: plain layered composition (no
AgentService wrapper, no new Hexagonal port), AGENT_TOOLS as the single
source-of-truth tuple, system_prompt= keyword verified against the installed
langchain==1.4.0 API, prompt-as-prose decision policy (no hardcoded Python
branch), per-call InMemorySaver default, distinct adjustment_amount vs
delta_pct naming to prevent model conflation, create_erp_adjustment /
notify_human staying in app/tools/ with app/agent/ importing inward only.
No deviations found.

## Final Verdict

PASS for PR 1 scope (Phases 1-4 + tests 5.1/5.2). 264/264 tests passing
(228 pre-existing + 36 new, zero regressions), all eight targeted attention items
independently confirmed at both the test-evidence and source-code level. Zero
CRITICAL or WARNING issues; one non-blocking SUGGESTION (stale design.md checkbox).
Recommend sdd-archive for PR 1; PR 2 (feature/f-b5-agent-core-integration, test
5.3 + README) requires its own apply + verify cycle, following the F-B4 precedent.
