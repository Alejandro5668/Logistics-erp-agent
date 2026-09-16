# Verification Report - F-B6 FastAPI Streaming API, PR 2

**Change**: f-b6-fastapi
**Scope**: PR 2 only - app/api/routes/chat.py, app/api/routes/__init__.py, app/api/app.py, app/main.py, tests/test_api_endpoints.py, README.md. PR 1 (schemas/events/errors/dependencies/service/sse) already merged and verified separately (verify-report.md, untouched by this report).
**Branch**: feature/f-b6-fastapi-routes
**Mode**: Full artifact set (proposal + spec + design + tasks), source inspection + runtime test evidence.

## Completeness (tasks.md)

All Phase 1-4 tasks marked [x]. Phase 3 (routes/app/main/README) and Phase 4 (integration tests) are the PR 2 deliverables under review here; both are checked and match the code state on disk. No unchecked tasks - full verification proceeds.

## Test Evidence

| Command | Result |
|---|---|
| pytest tests/test_api_endpoints.py -v (implied by full run below) | 10/10 passed |
| pytest -v (full suite) | 332 passed, 0 failed (7.16s) |

322 pre-existing tests (F-B1-F-B5 + F-B6 PR 1's 48 test_api_service.py tests) + 10 new test_api_endpoints.py integration tests = 332. Zero regressions - pre-existing tests ran unmodified.

## Adversarial Checks (source-verified, not just test-name-verified)

1. Two-error-window contract is real.
chat() in app/api/routes/chat.py calls events = run_turn(...), then first_event = await events.__anext__() before constructing StreamingResponse. If that first pull raises, the exception is a plain, unhandled exception inside the route coroutine - it propagates to FastAPI's normal exception dispatch, which routes it to the centralized handlers registered in app/api/app.py (EXCEPTION_HANDLERS from app/api/errors.py) -> HTTP 502/503 JSON body, no stream opened. Nothing swallows it. For a later pull (inside _sse_body, after headers are already committed), the async-for loop over rest is wrapped in except (ProviderUnavailableError, AgentExecutionError), converting it into a terminal ErrorEvent SSE frame instead of crashing the stream. run_turn() (app/api/service.py) never raises a bare exception - its own except Exception block always re-raises via _classify_exception(exc), so the router's two-window catch is exhaustive by construction. Confirmed genuine, not documentation-only.

2. /chat/sync shares the exact same run_turn() call.
chat_sync() calls run_turn(request, agent, registry) directly - the identical call used by /chat. It folds events with no divergent guardrail/tool logic: ContentEvent appends and concatenates; BlockedEvent replaces prior content parts with the safe message (REPLACE semantics, matching the spec Blocked-Turn Replace Semantics requirement even on the non-streaming transport); DoneEvent captures final thread_id/status. No reimplementation found.

3. Role/guardrail integration test proves something real.
TestRoleGuardrailIntegration builds a real build_agent() with a ScriptedChatModel proposing a restricted-field (salary) create_erp_adjustment tool call. The EMPLOYEE-role test asserts the event name list equals only blocked and that salary is absent from the payload (no field-name leak). The ADMIN-role test uses the identical restricted-field proposal, asserts blocked is not in the event names and the terminal event is done. Both assert on actual SSE event names/content, not merely no exception raised.

4. Thread-continuity test proves real session memory over HTTP.
test_second_turn_reuses_first_turns_tool_result_without_recalling_it sends two sequential POST /chat/sync requests sharing thread_id=t-continuity against a ScriptedChatModel with exactly 3 scripted responses (tool_call + final for turn 1, one final for turn 2). It asserts model.index == 3 - since ScriptedChatModel raises AssertionError on any unscripted step, this proves get_erp_data was NOT re-invoked on turn 2 - and asserts a ToolMessage is present in model.seen[-1], confirming the checkpointed state (including the tool result) was replayed into turn 2's context. This mirrors F-B5's own TestL4MemoryContinuity pattern, now driven entirely through HTTP. Genuine continuity proof, not just both requests succeeded.

5. app.dependency_overrides[get_agent] used correctly.
_client_with_agent() in tests/test_api_endpoints.py sets app.dependency_overrides[get_agent] to a lambda returning the test double agent, and app.dependency_overrides[get_thread_registry] similarly, on a fresh create_app() instance per test. get_agent() is never called directly. Matches app/api/dependencies.py's documented guidance (a direct call would attempt build_agent() with no model override, requiring real provider credentials).

6. Error-window tests assert real status codes and real body content.
- test_provider_failure_before_first_byte_returns_http_502_or_503: asserts response.status_code in (502, 503) and that timed out is absent from the JSON body's message field (no provider-internal leak). TimeoutError classifies to ProviderUnavailableError (503) via _classify_exception's _PROVIDER_ERROR_TYPES tuple - consistent.
- test_provider_failure_before_first_byte_on_sync_endpoint_also_maps_to_http_error: ValueError raised with message graph exploded asserts status_code == 502 - correctly falls through to AgentExecutionError since ValueError is not in _PROVIDER_ERROR_TYPES and its message contains no provider keyword. Consistent with _classify_exception's logic, not a coincidental match.
- test_provider_failure_after_headers_sent_yields_terminal_error_sse_event: asserts status_code == 200 (headers already committed), the event name list equals content then error, and parses the terminal frame's JSON body to assert error_payload code equals provider_unavailable and that dropped is absent from the message. Asserts actual SSE body content, not merely request completion.

7. Zero regressions. All 322 pre-existing tests (F-B1-F-B6 PR 1) pass unmodified alongside the 10 new tests; full suite 332/332 green.

8. README.md accuracy. The new API HTTP (F-B6) section documents the command uvicorn app.main:app --reload, which matches app/main.py's actual app = create_app() module-level binding (app.main:app is the correct ASGI target). Both curl examples use syntactically valid JSON bodies matching the ChatRequest schema (message, thread_id, role fields). The documented progress event label Looking up ERP order data matches TOOL_LABELS[get_erp_data] verbatim in app/api/service.py. The error-handling section accurately describes the two-window HTTP-502/503-vs-terminal-SSE-error-event contract, consistent with the verified implementation above.

## Spec Compliance Matrix (PR 2-relevant requirements)

| Requirement | Scenario | Status | Evidence |
|---|---|---|---|
| Chat Endpoint Contracts | Streaming/non-streaming completes normally | PASS | TestChatEndpointReachableAndShaped (4 tests) |
| No Unguarded Content Reaches the Client | sink logic, PR 1 owned, exercised end-to-end here | PASS | TestRoleGuardrailIntegration, TestChatEndpointReachableAndShaped |
| Progress Events During Tool Execution | Tool call emits label-only progress | PASS | README example cross-checked against TOOL_LABELS; unit-covered in PR 1 |
| Blocked-Turn Replace Semantics | Output blocked after partial content / input blocked before generation | PASS | TestRoleGuardrailIntegration::test_employee_role_is_blocked_with_terminal_blocked_event |
| Role and Thread_id Propagation | Role changes guardrail outcome / thread continuity | PASS | TestRoleGuardrailIntegration (both tests), TestThreadContinuity |
| Failure Handling and Checkpointer Safety | Pre-first-byte HTTP error / post-headers terminal error event / graph-layer exception does not corrupt state | PASS | TestErrorWindows (3 tests); checkpointer-safety generation-remap unit-verified in PR 1, exercised transitively here |

## Design Coherence

- Two endpoints, one path: confirmed - chat_sync() calls the same run_turn(), no divergent logic.
- Two error windows: confirmed genuine via source trace (peek-before-StreamingResponse, try/except in _sse_body), not just documented.
- Guarded sink granularity / stream_mode=updates only / progress from approved tool-call names: PR 1-owned, exercised transitively through the real-agent integration tests here (role/guardrail, thread continuity) with no evidence of drift.
- File Changes table: all PR 2 files present and match description (routes/chat.py, app.py, main.py, README.md, tests/test_api_*.py).

## Issues

CRITICAL: None.
WARNING: None.
SUGGESTION: None.

## Final Verdict: PASS

All 8 adversarial checks confirmed genuine (not documentation-only or test-name-only). The two-error-window contract, shared run_turn() path, role/guardrail blocking, thread continuity, dependency-override test isolation, and README accuracy all verified against source, not assumed from names or comments. Full suite 332/332 passing with zero regressions. This closes out the full technical implementation of Track B (F-B1-F-B6).
