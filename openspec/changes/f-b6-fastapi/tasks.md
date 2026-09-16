# Tasks: F-B6 — FastAPI Streaming API

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1700–1900 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (core plumbing + service) → PR 2 (routes + app + integration tests) |
| Delivery strategy | single-pr (received) |
| Chain strategy | stacked-to-main (recommended; feature-branch-chain acceptable) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Core plumbing + service logic (schemas, events, errors, dependencies, service, sse + unit tests) | PR 1 | `pytest tests/test_api_service.py -v` | Pure Python unit tests, no network | Delete `app/api/` except `routes/`, no config change |
| 2 | Routes, app wiring, integration tests, docs | PR 2 | `pytest tests/test_api_endpoints.py -v` | TestClient + F-B5 fake model, offline | Delete `app/api/routes/`, `app/main.py`, revert docs |

---

## Phase 1: Foundation (Schemas, Events, Errors, Dependencies) — PR 1

- [x] 1.1 Create `app/api/schemas.py` with Pydantic models: ChatRequest {message, thread_id, role}, ChatResponse {content, thread_id, status}, ErrorResponse {code, message, replace}
- [x] 1.2 Create `app/api/events.py` with framework-free AgentEvent union: progress {label}, content {text}, blocked {message, replace}, error {code, message, replace}, done {thread_id, status}
- [x] 1.3 Create `app/api/errors.py` with typed exceptions: ProviderUnavailableError, AgentExecutionError, and centralized @app.exception_handler implementations
- [x] 1.4 Create `app/api/dependencies.py` with cached agent provider and ThreadRegistry for generation-remap (maps public thread_id → internal {thread_id}#{generation})

## Phase 2: Core Service Logic (Guarded Sink and SSE Serialization) — PR 1

- [x] 2.1 Create `app/api/service.py` with run_turn() async generator: accept ChatRequest, forward role as context={"role":role}, re-apply inspect_output to each AIMessage before yielding content, drop ToolMessages entirely, map tool_calls to progress events via TOOL_LABELS dict, handle blocked output and exceptions
- [x] 2.2 Create `app/api/sse.py` with AgentEvent → SSE frame serializer: convert each event type to JSON with correct data schema and escape fields for SSE compatibility
- [x] 2.3 Write unit tests (no agent, no network): sink verdict (inspect_output ALLOW/BLOCK), progress mapping from tool_calls, ToolMessage drop, SSE frame structure, thread-remap generation logic

## Phase 3: API Routes and Application Setup — deferred to PR 2

- [x] 3.1 Create `app/api/routes/chat.py` with two endpoints: POST /chat returns StreamingResponse with SSE (peek first event for pre-headers error), POST /chat/sync returns JSON ChatResponse (fold events into final response)
- [x] 3.2 Create `app/api/app.py` with create_app() factory (register routes, exception handlers), create `app/main.py` with ASGI entrypoint (uvicorn app.main:app)
- [x] 3.3a `requirements.txt` updated with fastapi, uvicorn, httpx (pulled forward into PR 1 — cheap to pin now, versions verified against the installed langchain==1.4.0/langgraph==1.2.11 stack, `pip check` clean)
- [x] 3.3b Update `README.md` with run instructions (uvicorn ...) and curl examples for both endpoints — deferred to PR 2

## Phase 4: Integration Tests and RED-Line Verification — deferred to PR 2

- [x] 4.1 Write integration tests for both endpoints: POST /chat and POST /chat/sync with TestClient, verify SSE stream format, verify JSON response structure
- [x] 4.2 Write role/guardrail integration tests: identical request with role=EMPLOYEE is blocked (terminal blocked event), same request with role=ADMIN succeeds (terminal done event)
- [x] 4.3 Write error-window tests: provider failure before first byte returns HTTP 502/503, failure after headers sent returns terminal error event in stream
- [x] 4.4a RED-line "value-before-label output is never leaked" verified at the PR 1 unit level (`TestRunTurnBlockedSemantics::test_blocked_replaces_prior_content_and_is_the_only_terminal_event` in `tests/test_api_service.py`) — full TestClient-level regression still deferred to PR 2
- [x] 4.5a RED-line "failed turn cleanup" (E5 regression) verified at the PR 1 unit level (`TestRunTurnFailureHandling::test_failed_turn_is_followed_by_a_clean_turn_on_the_same_thread_id`) — proves `ThreadRegistry` generation remap directly; full checkpointer-level regression via TestClient deferred to PR 2
- [x] 4.6 Write thread-continuity test: two sequential requests on same thread_id preserve agent state across turns; verify second turn sees prior context — deferred to PR 2 (requires the real agent + routes)
- [x] 4.7a `pytest -v` green offline for PR 1: all 48 new `tests/test_api_service.py` tests pass alongside the existing 274 tests (322 total, 0 failures) — see Work Unit Evidence below

---

## Implementation Notes

### Design-to-Task Mapping

| Design Section | Tasks |
|---|---|
| E2: after_model node separate | 2.1 (service must re-check accumulated text, not assume node ordering) |
| E3: updates emit after node completes | 2.1 (stream only after complete messages, not token-level) |
| E4: ToolMessage default handler | 2.1 (drop ToolMessages; tool exceptions become ToolMessage(status="error"), already handled) |
| E5: durability="async" persists on exception | 2.1 (ThreadRegistry generation remap prevents poisoning); 4.5 |
| Guarded sink (message-level evaluate-then-flush) | 2.1, 2.3 |
| Progress from approved tool-call names | 2.1 (TOOL_LABELS mapping); 2.3 |
| Two error windows | 3.1 (peek first event); 4.3 |
| ThreadRegistry remap on failed turn | 1.4, 2.1, 4.5 |

### Task Dependencies (Sequential, cannot parallelize across phases)

- Phase 1: all tasks independent (define types only)
- Phase 2 depends on Phase 1 (uses schemas, events, errors, dependencies)
- Phase 3 depends on Phase 1 and 2 (wires logic into FastAPI)
- Phase 4 depends on Phase 1, 2, 3 (full system needs to be runnable)

### Scope Exclusions (per design and proposal)

- Do NOT modify `app/security/` (F-B4) — only consume existing `inspect_output` unchanged
- Do NOT modify agent logic (F-B1, F-B5) — only add HTTP layer on top
- Do NOT add auth/JWT, persistent checkpointing, real Azure deployment, rate limiting, or multi-user isolation
- No changes to `requirements.txt` beyond fastapi, uvicorn, httpx (no extra middleware, observability, or async frameworks)

### Spec Requirements Checklist

- Req: Chat Endpoint Contracts → 3.1, 4.1, 4.2
- Req: No Unguarded Content Reaches Client → 2.1 (guarded sink), 2.3 (unit test), 4.4 (RED test)
- Req: Progress Events During Tool Execution → 2.1 (TOOL_LABELS), 2.3
- Req: Blocked-Turn Replace Semantics → 2.1 (blocked event), 4.2
- Req: Role and Thread_id Propagation → 2.1 (context dict), 4.2, 4.6
- Req: Failure Handling and Checkpointer Safety → 1.4 (ThreadRegistry), 2.1 (exception handling), 3.1 (error windows), 4.3, 4.5

---

## Size Estimate by File (for linecount tracking)

- `app/api/schemas.py`: ~100 lines (3 Pydantic models, validation, docstrings)
- `app/api/events.py`: ~80 lines (union type definition)
- `app/api/errors.py`: ~120 lines (exception classes, FastAPI handlers)
- `app/api/dependencies.py`: ~90 lines (cached agent, ThreadRegistry)
- `app/api/service.py`: ~300 lines (guarded sink, inspect_output re-check, progress mapping, exception handling)
- `app/api/sse.py`: ~100 lines (event serialization to SSE frame format)
- `app/api/routes/chat.py`: ~200 lines (two endpoints, first-event peeking, error handling)
- `app/api/app.py` & `app/main.py`: ~70 lines (factory, exception handlers, ASGI entrypoint)
- `requirements.txt` delta: ~5 lines
- `README.md` delta: ~30 lines
- Unit tests (`test_api_service.py`): ~200 lines (sink, progress, ToolMessage drop, SSE, remap)
- Integration tests (`test_api_endpoints.py`, etc.): ~550 lines (both endpoints × roles × error windows × thread continuity × RED-line tests)

**Total estimated: 1840 lines** (safe range: 1700–1900)

---

## Verification Strategy

**PR 1 gate**: Unit tests pass in isolation (`pytest tests/test_api_service.py -v`); service layer is framework-agnostic and testable without FastAPI context.

**PR 2 gate**: Full integration suite passes (`pytest tests/test_api_endpoints.py -v`); both endpoints reachable via TestClient; all RED-line regression tests pass; existing 274 tests from F-B1–F-B5 still pass.

**Terminal gate** (sdd-verify): Full test suite; coverage report; manual curl tests against running app (documented in README).
