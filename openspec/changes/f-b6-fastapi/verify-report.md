# Verification Report - F-B6 FastAPI Streaming API (PR 1 scope)

**Change**: `f-b6-fastapi`
**Scope**: PR 1 only - Phases 1-2 (schemas, events, errors, dependencies, service, sse) + unit tests. Routes/app/integration tests are Phase 3-4, explicitly deferred to PR 2; their absence is NOT flagged here.
**Branch**: `feature/f-b6-fastapi` (confirmed, not main)
**Mode**: openspec-only (Engram unavailable this session)

## Completeness (Tasks)

All PR 1 tasks checked and verified against code:

| Task | Status | Evidence |
|---|---|---|
| 1.1 schemas.py | done | `app/api/schemas.py` - ChatRequest/ChatResponse/ErrorResponse present, matches spec fields |
| 1.2 events.py | done | `app/api/events.py` - 5-member AgentEvent union, class-level type discriminators |
| 1.3 errors.py | done | `app/api/errors.py` - ProviderUnavailableError(503)/AgentExecutionError(502), generic safe messages, EXCEPTION_HANDLERS map |
| 1.4 dependencies.py | done | `app/api/dependencies.py` - get_agent() lru_cache singleton, ThreadRegistry with threading.Lock |
| 2.1 service.py | done | `app/api/service.py` - run_turn() guarded sink |
| 2.2 sse.py | done | `app/api/sse.py` - format_sse() |
| 2.3 unit tests | done | `tests/test_api_service.py` - 48 tests |
| 3.3a requirements.txt | done | fastapi, uvicorn, httpx pinned with verified-installed comments |
| 4.4a RED value-before-label | done | TestRunTurnBlockedSemantics::test_blocked_replaces_prior_content_and_is_the_only_terminal_event |
| 4.5a RED E5 checkpointer regression | done | TestRunTurnFailureHandling::test_failed_turn_is_followed_by_a_clean_turn_on_the_same_thread_id |
| 4.7a pytest green | done | 322/322 passing (see below) |

No unchecked PR-1 task found. Phase 3 (routes/app), Phase 4.1/4.2/4.3/4.6 (integration tests) correctly remain unchecked - PR 2 scope, not evaluated.

## Test Execution Evidence

pytest -v : 322 passed, 1062 warnings in 11.86s
pytest tests/test_api_service.py -v : 48 passed in 0.80s
pytest --collect-only -q : 322 tests collected

274 pre-existing (F-B1 through F-B5) + 48 new = 322. Zero failures, zero regressions. git diff main...HEAD --stat -- app/security app/agent returns empty - F-B4/F-B5 source untouched, confirming the no-edit-to-F-B1..F-B5-logic scope constraint.

## Adversarial Security Review (R4/R5 closure - this PR core purpose)

1. stream_mode="updates", not "messages" - PASS. app/api/service.py:208 - agent.astream(..., stream_mode="updates"); test asserts kwargs["stream_mode"] == "updates" (test_role_and_thread_id_are_forwarded_to_astream).

2. inspect_output called on every complete AIMessage before any ContentEvent/ProgressEvent yield - PASS. service.py:227-243 - iterates node_value["messages"]: ToolMessage skipped, non-AIMessage skipped; builds payload = _to_agent_output(message); decision = inspect_output(payload, role); BLOCK yields BlockedEvent and breaks; only when decision is not BLOCK does ContentEvent/ProgressEvent get yielded. No code path yields text before inspect_output returns for that message.

3. ToolMessages unconditionally dropped regardless of status - PASS. service.py:228-229 - if isinstance(message, ToolMessage): continue - no status branch, no path converts a ToolMessage to any event. Test: test_tool_messages_never_become_events (raw ERP row content never appears in emitted events).

4. Progress events carry only static TOOL_LABELS value, never raw name/args/results - PASS. tool_label() (service.py:99-101) does TOOL_LABELS.get(name, _DEFAULT_TOOL_LABEL); ProgressEvent(label=tool_label(tool_call.name)) (service.py:243) is the only construction site. Test: test_progress_events_never_carry_args_or_tool_name asserts neither the secret arg value nor the raw tool name string appears in the label.

5. jump_to == "end" detection is node-name-agnostic - PASS. service.py:214-222 - for node_value in update.values(): ... if node_value.get("jump_to") == "end": iterates every node update value in the chunk, not a hardcoded key/node name. Tests cover both SecurityGuardrailMiddleware.after_model and SecurityGuardrailMiddleware.before_model node names resolving identically, proving the check does not hardcode either.

6. ThreadRegistry.bump() called only on genuine exception, never on BLOCK - PASS. bump() is called exactly once, inside except Exception as exc: (service.py:247-249). The jump_to == "end" branch (service.py:218-222) sets blocked = True and yields BlockedEvent without raising or touching registry. Confirmed no other call site.

7. RED-line test_failed_turn_is_followed_by_a_clean_turn_on_the_same_thread_id genuinely proves the E5 fix - PASS. Read full test body (tests/test_api_service.py:492-520): turn 1 uses a scripted astream agent that raises TimeoutError; asserts ProviderUnavailableError propagates and captures turn_one_internal_id = "t-cleanup#0" from the actual astream() call kwargs. Turn 2 (fresh scripted agent, same public thread_id="t-cleanup") captures turn_two_internal_id = "t-cleanup#1" from its own astream() call kwargs, and asserts turn_one_internal_id != turn_two_internal_id plus turn 2 completes normally (ContentEvent + DoneEvent). This is a real before/after comparison of the internal thread id actually passed to astream config, not just an assertion on the test name.

8. aclose() called in finally regardless of exit path - PASS (impl) / WARNING (test). service.py:250-254 - finally: if stream is not None: aclose = getattr(stream, "aclose", None); if aclose is not None: await aclose(), unconditional on the branch taken (normal completion, BLOCK, or exception all fall through the same finally). However TestRunTurnStreamCleanup::test_underlying_stream_is_closed_after_the_turn_completes only asserts events is truthy - it does not spy on aclose to prove it was actually invoked. Test name overclaims relative to what it checks; production code is correct by direct inspection.

9. ThreadRegistry thread-safe (lock-guarded) - PASS. app/api/dependencies.py - self._lock = threading.Lock(); get_internal_thread_id, bump, current_generation all wrap dict access in with self._lock:.

10. Zero regressions in 274 pre-existing tests - PASS. Full pytest -v run: 322 passed, 0 failed. git diff main...HEAD --stat -- app/security app/agent empty.

## Spec Compliance (PR-1-applicable requirements only)

- Chat Endpoint Contracts: N/A, routes are PR 2. Correctly deferred.
- No Unguarded Content Reaches the Client: run_turn() guarded sink + unit tests (checks 2, 3, 4 above). COVERED at service layer; full end-to-end (via TestClient) deferred to PR 2 per plan.
- Progress Events During Tool Execution: tool_label() + TestRunTurnProgressMapping. COVERED.
- Blocked-Turn Replace Semantics: BlockedEvent(replace=True) always constructed with default; test_blocked_replaces_prior_content_and_is_the_only_terminal_event. COVERED.
- Role and Thread_id Propagation: context={"role": role} forwarded (service.py:199, asserted in test_role_and_thread_id_are_forwarded_to_astream); thread continuity across turns requires the real agent/routes (PR 2). Partially covered - role forwarding proven at unit level; end-to-end continuity deferred to PR 2 (task 4.6, correctly unchecked).
- Failure Handling and Checkpointer Safety: _classify_exception, ThreadRegistry remap, RED-line E5 test. COVERED at service layer; HTTP-status two-window behavior needs the router (PR 2, task 3.1/4.3, correctly unchecked).

## Design Coherence

- stream_mode="updates" decision (design.md "Decision: stream_mode=updates only") - implemented exactly as specified, no deviation.
- Message-level evaluate-then-flush granularity (design.md "Decision: Guarded sink granularity") - implemented: sink re-runs inspect_output on the same complete AIMessage, no token-level flush anywhere in service.py.
- Progress-from-approved-tool-call-names decision - implemented via TOOL_LABELS.
- Checkpointer safety via thread generation remap - implemented via ThreadRegistry, bump() scoped correctly to genuine exceptions only.
- _message_text/_to_agent_output deliberately duplicated from app.security.middleware rather than imported (design.md stated layering rationale) - confirmed in service.py docstrings, matches design intent, not an accidental drift.

No design deviations found for in-scope PR 1 code.

## Issues

CRITICAL: None.

WARNING:
1. TestRunTurnStreamCleanup::test_underlying_stream_is_closed_after_the_turn_completes (tests/test_api_service.py:523-532) does not actually spy on or assert that aclose() was called - it only asserts the turn produced events. The test name promises stream-cleanup verification it does not perform. The production code (service.py:250-254) is correct by direct inspection, so this is a test-quality gap, not a functional defect. Recommend strengthening this test in PR 2 (for example wrap the scripted agent stream to record whether aclose was invoked) before relying on it as the sole regression guard for check 8.

SUGGESTION: None beyond the above.

## Final Verdict

PASS WITH WARNINGS (1 WARNING, 0 CRITICAL, 0 SUGGESTION)

PR 1 scope is complete, all tasks are checked and match code state, 322/322 tests pass with zero regressions to the 274 pre-existing F-B1-F-B5 tests, and all ten adversarial security checks on the R4/R5 closure - the safety-critical purpose of this change - pass by direct source and control-flow inspection plus runtime-proven test evidence. The single WARNING is a test-assertion weakness (not a production defect) safe to carry into PR 2 rather than block this slice.

Recommend proceeding to sdd-archive for this PR 1 slice, or continuing to PR 2 (Phase 3-4: routes, app wiring, integration tests) per the chained-PR plan in tasks.md.
