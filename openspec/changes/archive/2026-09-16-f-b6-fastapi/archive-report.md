# Archive Report: F-B6 — FastAPI Streaming API

## Summary

The final Track B feature: exposes the F-B5 agent over HTTP with SSE streaming, delivered as
**two chained PRs** (user-approved split — the single-PR estimate of 1700–1900 lines was the
largest in the project and exceeded the 400-line review budget by far):

- **PR 1** ([#8](https://github.com/Alejandro5668/Logistics-erp-agent/pull/8), merged) — the
  guarded sink: `app/api/schemas.py`, `events.py`, `errors.py`, `dependencies.py`, `service.py`
  (`run_turn()`), `sse.py`. No HTTP routes yet.
- **PR 2** ([#9](https://github.com/Alejandro5668/Logistics-erp-agent/pull/9), merged) —
  `app/api/routes/chat.py` (`POST /chat` SSE, `POST /chat/sync` JSON), `app/api/app.py`,
  `app/main.py`, end-to-end integration tests, README.

## Final State

- All 17 tasks across both PRs complete (`tasks.md`).
- Both `sdd-verify` passes: PASS (PR 1: 0 CRITICAL, 1 non-blocking WARNING on test-assertion
  strength; PR 2: 0 CRITICAL, 0 WARNING, 0 SUGGESTION — the cleanest verify pass in the project).
- `pytest -v` on `main` after both merges: **332/332 passing** (274 from F-B1-F-B5 + 48 PR 1 +
  10 PR 2).
- This PR's own verify pass (PR 2) closes out **Track B in full** — F-B1 through F-B6 are all
  exercised together for the first time via real HTTP requests through `TestClient`.

## The Real Security Finding (this feature's reason to exist)

F-B4's own design had documented two residual risks explicitly as "hard constraints on F-B6":
- **R4**: if the API streams the model's tokens directly, the output-side guardrail
  (`after_model`) — which runs only after the model node fully completes — could not evaluate
  content before it left the process.
- **R5**: raw tool output must never reach the client without passing through the guardrail.

F-B6's design phase **empirically verified** (live execution against the installed
`langchain==1.4.0`/`langgraph==1.2.11`, not just source reading) that `stream_mode="messages"`
does leak token-level content before the guardrail's node exists — confirming R4 as a genuine,
concrete vulnerability, not a theoretical one. The fix: `stream_mode="updates"` only, combined
with a **guarded sink** that re-applies the same pure `inspect_output` (unmodified from F-B4) to
every complete `AIMessage` before any content is emitted, and unconditional dropping of every
`ToolMessage` (closing R5). Progress events carry only static labels from a fixed catalog, never
raw tool names, arguments, or results.

## Other Notable Engineering Findings

- **Checkpointer poisoning (E5)**: LangGraph's default `durability="async"` persists partial
  state even when a mid-turn exception propagates — a failed turn could leave a thread's
  checkpoint holding an `AIMessage` with unmatched `tool_calls`, a shape most providers reject on
  the next turn. Fixed with `ThreadRegistry`, mapping the public `thread_id` to an internal
  `{thread_id}#{generation}` that bumps on any genuine exception (never on a guardrail BLOCK,
  which is a clean graph termination) — thread-safe, lock-guarded.
- **Two-error-window HTTP contract**: the `/chat` route peeks the first `run_turn()` event before
  constructing `StreamingResponse` — a pre-first-byte failure becomes a real HTTP 502/503; a
  failure after headers are already sent becomes a terminal SSE `error` event instead (the status
  code can no longer change once bytes are on the wire).
- **PR 1's apply agent hit a session limit mid-task** (external tooling constraint, not a project
  finding) — all source files and the full 48-test unit suite were already complete and verified
  passing at that point; the orchestrator resumed directly (no sub-agent), reviewed the code,
  confirmed the suite, and made the 4 logical commits the agent hadn't gotten to yet. No rework
  was needed.

## Spec Merge

`agent-api` is a new capability — full spec published to `openspec/specs/agent-api/spec.md` (no
prior version to delta against).

## Consumers

None — this is the top of the dependency graph. `app/main.py` (`uvicorn app.main:app`) is the
project's actual runnable entrypoint, documented in `README.md` with curl examples for both
endpoints.

## Track B Status

With F-B6 archived, all six Track B features (F-B1 mock ERP data, F-B2 tax discrepancy, F-B3 RAG
pipeline, F-B4 security guardrail, F-B5 agent core, F-B6 FastAPI streaming API) are complete,
merged, and archived. Combined with Track A (F-A1-F-A4, documentation), the project's full
technical scope per `docs/00-planning.md` is done. Remaining work is delivery-only: top-level
`README.md` polish and the 5-minute demo video.
