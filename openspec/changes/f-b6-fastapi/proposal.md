# Proposal: F-B6 — FastAPI Streaming API (LLM/ERP error handling, guarded delivery)

## Intent

`build_agent()` (F-B5) is runnable but unreachable: nothing exposes it over HTTP, so the prototype
has no demo surface and no answer to the rubric's Parte 2.3 ("endpoint FastAPI + streaming de tokens
+ ¿qué responde el sistema si el LLM falla o el ERP no responde?"). F-B6 is also the first place a
**real caller-supplied `role`** reaches F-B4's `_role_from_context`, and the place where F-B4's
residual risks **R4 (streaming bypasses `after_model`)** and **R5 (raw tool output rendered
unguarded)** stop being theoretical. This is the last Track B feature — the project's delivery edge.

## Scope

### In Scope
- `app/api/`: FastAPI app + `POST /chat` accepting `{message, thread_id, role}`; `role` is forwarded
  as `context={"role": ...}`, exactly the shape `_role_from_context` reads (dict → `.get("role")`).
- SSE `StreamingResponse` with an explicit, versioned event protocol (progress / content / terminal
  error-or-block events) — not an undocumented token firehose.
- **R4/R5 closure**: only guardrail-approved content is ever flushed to the socket. Raw tool output is
  never streamed; model text is streamed only behind an output-side check at the stream sink.
- Error handling for both rubric failure modes: (a) provider failure — timeout, rate limit, auth,
  network; (b) tool/ERP failure at LangGraph's tool-execution layer. Both yield a generic client-safe
  message that never echoes provider internals, stack traces, or ERP rows.
- Offline tests via FastAPI `TestClient` + F-B5's scripted fake model: no network, no credentials.

### Out of Scope
- Auth/JWT — `role` stays client-supplied and spoofable (F-B4 R1, accepted for the prototype).
- Real Azure deployment/infra (F-A3); persistent checkpointer; rate limiting; multi-user isolation
  beyond caller-supplied `thread_id`.
- Any edit to F-B1..F-B5 logic. F-B1's never-raises contract is **not** weakened; the API simply
  stops *assuming* it for the whole tool node.

## Capabilities

### New Capabilities
- `agent-api`: HTTP request contract, SSE event protocol, streaming lifecycle, error taxonomy and
  client-safe failure responses.

### Modified Capabilities
- `security-guardrail`: add a delivery-boundary requirement closing R4/R5 — no bytes reach the client
  unless output-side inspection has passed for the accumulated content, and raw tool output is never
  rendered directly.

## Approach

One thin HTTP adapter over `build_agent()`; no re-implementation of agent logic. The stream is driven
by LangGraph's async stream, but the API owns a **guarded sink**: it accumulates model text and
re-applies `inspect_output` before each flush, emits tool activity only as opaque progress events
(never payloads), and on BLOCK terminates the stream with F-B4's safe message. Two failure windows
are treated differently on purpose: a failure **before the first byte** returns a real HTTP status;
**after** the SSE headers are committed it must become a terminal in-stream `error` event, since the
status code can no longer change.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/api/` | New | FastAPI app, `/chat` route, SSE sink, error mapping |
| `app/main.py` | New | ASGI entrypoint (`uvicorn app.main:app`) |
| `tests/test_api_*.py` | New | TestClient + fake-model streaming/error/guardrail tests |
| `requirements.txt` | Modified | `fastapi`, `uvicorn`, `httpx` (TestClient) |
| `README.md` | Modified | Run + curl instructions (delivery checklist) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| **R4 made concrete**: token-level streaming flushes model text before `after_model` runs | High | Guarded sink re-checks accumulated text pre-flush; if LangGraph's event granularity makes this unsound, fall back to post-guardrail chunked delivery and document the UX tradeoff explicitly — never ship silent token-level bypass |
| Residual R4′: already-flushed tokens cannot be recalled from the client | Med (accepted) | Only harmless prefixes can escape; protocol contract states a terminal block event supersedes prior content events; document, do not hide |
| R5: tool output leaking via progress events | Med | Progress events carry tool *name/status* only, never args or results |
| Stream-sink guardrail cost per flush | Low | `inspect_output` is pure compiled-regex; batch per chunk, not per character |
| SSE status-code trap (errors after headers sent) | Med | Explicit two-window error contract; tested in both windows |
| `thread_id` is caller-supplied — cross-caller memory leak (F-B5 flagged this for F-B6) | Med | Document as prototype limit alongside R1; no server-side session forgery fix in this slice |
| LangGraph stream API drift (F-B3/F-B4/F-B5 all hit version drift) | Med | Verify stream modes and event shapes against the installed `langgraph` at design/apply time, per precedent |

## Rollback Plan

Fully additive and reversible: delete `app/api/`, `app/main.py`, and the new tests; revert the
`requirements.txt` and `README.md` lines; or drop `feature/f-b6-fastapi`. No schema change, no
migration, no persisted state (`InMemorySaver` dies with the process) and no ERP write path is added,
so nothing financial can be left inconsistent (CLAUDE.md "Superficies sensibles"). F-B1..F-B5 are
untouched, so their 274 passing tests are the regression net.

## Dependencies

- F-B5 (`build_agent`) and F-B4 (`build_security_middleware`, `inspect_output`) — merged.
- `fastapi`, `uvicorn`, `httpx`; no live LLM credentials required for tests.

## Success Criteria

- [ ] `POST /chat` returns an SSE stream; first event arrives before the agent run completes.
- [ ] Caller-supplied `role` reaches the guardrail — an `EMPLOYEE` restricted-field request ends the
      stream with the safe message; the same request as `ADMIN` is allowed.
- [ ] No raw tool output and no unguarded model text is ever present in the emitted byte stream.
- [ ] Provider failure (timeout / rate limit / auth) yields a generic client-safe failure in both
      windows — pre-first-byte as an HTTP status, post-headers as a terminal in-stream event.
- [ ] A tool raising inside the agent loop yields the same client-safe failure, with F-B1's own
      never-raises contract and tests unchanged.
- [ ] Two turns on the same `thread_id` preserve session continuity across requests.
- [ ] `pytest -v` green offline; existing 274 tests still pass.
