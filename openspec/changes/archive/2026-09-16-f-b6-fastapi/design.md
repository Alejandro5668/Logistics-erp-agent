# Design: F-B6 — FastAPI Streaming API

## Technical Approach

Plain layered adapter (`architecture-patterns` gate: one integration, no new invariants) —
`router → service → build_agent()`. Nothing in `app/api/` re-implements agent or guardrail logic.

**Empirical verification** (installed `langgraph 1.2.11`, `langchain 1.4.0`, `langchain-core 1.6.3`,
`langgraph-checkpoint 4.2.0`; versions read from `site-packages/*.dist-info`, source inspected — no
shell in this phase, so `pip show` was replaced by direct package inspection):

| # | Finding | Evidence |
|---|---|---|
| E1 | Stream modes: `values, updates, checkpoints, tasks, debug, messages, custom` | `langgraph/types.py:122` |
| E2 | `after_model` is a **separate node**: `add_edge("model", f"{m.name}.after_model")` | `langchain/agents/factory.py:1616,1789` |
| E3 | `updates` emits **after a node completes**; a `None` return still yields `{node: None}` | `langgraph/pregel/_io.py:118-174` |
| E4 | ToolNode default `handle_tool_errors` is a callable → tool exceptions become `ToolMessage(status="error")`, they do **not** raise out of `astream` | `langgraph/prebuilt/tool_node.py:753`; `factory.py:1088` |
| E5 | Default `durability="async"`; `_suppress_interrupt` persists checkpoint **and** pending writes even on exception | `pregel/main.py:2603`; `pregel/_loop.py:1324-1334` |

E2 is decisive: token-level `messages` events and the `model` node's own `updates` both fire **before**
the guardrail hook exists as a node.

## Architecture Decisions

### Decision: Guarded sink granularity (R4 closure)

**Choice**: message-level **evaluate-then-flush**, re-chunked *after* approval for progressive UX.
**Alternatives**: token-level guarded sink (re-check accumulated prefix per flush).
**Rationale**: `inspect_output` matches field *labels* through `\b`-anchored normalized regexes
(`roles.py:118-144`). A label is unmatched on an incomplete prefix, and a restricted **value can precede
its label** ("…4402, that's the bank account"): a prefix-guarded flush emits the value before the block
fires. Unsound → spec's mandated fallback applies. The chosen sink runs the *same pure*
`inspect_output`, on the *same complete* `AIMessage`, with the *same* role as `after_model`; determinism
makes the verdicts identical, so a sink-ALLOW can never precede a middleware BLOCK. No node-name coupling.

### Decision: `stream_mode="updates"` only

**Alternatives**: `messages` (unguarded by construction, E2); `values` (resends full state per step);
`tasks` (payload carries raw tool results — R5 hazard); `custom` (requires writes from nodes we don't own).
**Rationale**: `updates` is the only mode that delivers complete, inspectable messages incrementally (E3).

### Decision: Progress from approved tool-call names

**Choice**: after a message passes the sink, emit one `progress` per `tool_call.name` mapped through a
static `TOOL_LABELS` dict; unknown name → generic label. `ToolMessage`s are dropped entirely.
**Rationale**: closes R5 — no arg, result or model-authored string ever reaches the wire.

### Decision: Two endpoints, one path

`run_turn()` is an async generator of framework-free `AgentEvent`s. `/chat` serializes them to SSE;
`/chat/sync` folds them into `ChatResponse`. Guardrail logic exists once (spec: Single Guarded Path).

### Decision: Two error windows

Service raises typed `ProviderUnavailableError` / `AgentExecutionError`. The router **peeks the first
event** before returning `StreamingResponse`: a pre-first-byte failure becomes HTTP 502/503 through a
centralized `@app.exception_handler`; after the first yield everything becomes a terminal `error` event.

### Decision: Checkpointer safety via thread generation remap

**Rationale**: per E5 a mid-turn exception still persists the superstep checkpoint plus pending writes, so
a thread can be left holding an `AIMessage` with `tool_calls` and no matching `ToolMessage`s — a shape most
providers reject, poisoning every later turn on that `thread_id`.
**Choice**: `ThreadRegistry` maps public `thread_id` → internal `{thread_id}#{generation}`; a failed turn
bumps the generation, so the next request starts from a clean checkpoint.
**Alternatives**: `durability="exit"` (no help — `_suppress_interrupt` persists regardless);
`update_state` rollback (couples to checkpoint internals for a prototype using `InMemorySaver`).

## Data Flow — one streaming request

```
client  router(/chat)   service.run_turn        agent.astream(updates)   guarded sink
  │ POST │              │                       │                        │
  │─────►│ Pydantic 422 │                       │                        │
  │      │─────────────►│ thread=registry.get() │                        │
  │      │              │ context={"role":role} │                        │
  │      │              │──────────────────────►│                        │
  │      │              │   {before_model: ...} │  (jump_to? → blocked)   │
  │      │              │◄──────────────────────│                        │
  │      │              │   {model: {messages}} │──── inspect_output ───►│ ALLOW?
  │      │◄─ 1st event ─│                       │        BLOCK ──────────┤→ blocked(replace)
  │◄ 200 │ headers sent │                       │                        │
  │◄ progress ──────────│ (static labels from approved tool_calls)       │
  │◄ content ───────────│ (approved text, re-chunked)                    │
  │      │              │   {tools: ToolMessage}│  ← DROPPED (R5)        │
  │      │              │   {model: {messages}} │──── inspect_output ───►│
  │◄ content ───────────│                       │                        │
  │◄ done ──────────────│                       │                        │
        exception at any point after headers → error(replace) + close; before → HTTP 5xx
```

Nothing crosses the socket that has not already passed `inspect_output`.

## File Changes

| File | Action | Description |
|---|---|---|
| `app/api/schemas.py` | Create | `ChatRequest{message,thread_id,role}`, `ChatResponse{content,thread_id,status}`, `ErrorResponse` |
| `app/api/events.py` | Create | Framework-free `AgentEvent` union: progress/content/blocked/error/done |
| `app/api/service.py` | Create | `run_turn()` — guarded sink, progress mapping, exception classification |
| `app/api/sse.py` | Create | `AgentEvent` → SSE frame serializer |
| `app/api/errors.py` | Create | Typed exceptions + centralized handlers |
| `app/api/dependencies.py` | Create | `Depends()` providers: cached agent, `ThreadRegistry` |
| `app/api/routes/chat.py` | Create | `POST /chat` (SSE), `POST /chat/sync` (JSON) |
| `app/api/app.py` / `app/main.py` | Create | `create_app()` factory; ASGI entrypoint |
| `tests/test_api_*.py` | Create | TestClient + fake-model suites |
| `requirements.txt`, `README.md` | Modify | `fastapi`, `uvicorn`, `httpx`; run/curl docs |

## Interfaces / Contracts

```
event: progress | content | blocked | error | done
data:  {"label": "..."} | {"text": "..."} |
       {"message": "...", "replace": true} |
       {"code": "provider_unavailable|agent_error", "message": "...", "replace": true} |
       {"thread_id": "...", "status": "ok"}
```

`replace: true` is the REPLACE semantic: the client MUST discard all prior `content` for that turn.
Exactly one terminal event (`blocked | error | done`) per stream.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | sink verdict, progress mapping, ToolMessage drop, SSE framing, thread remap | pure functions, no agent |
| Integration | both endpoints, EMPLOYEE vs ADMIN, blocked-replace, both error windows, thread continuity | TestClient + F-B5 fake model |
| E2E | N/A — no live provider offline |

RED tests must include: value-before-label output is never leaked; a failed turn is followed by a clean
turn on the same `thread_id` (E5 regression).

## Threat Matrix

N/A — no routing/shell/subprocess/VCS/PR-automation/executable-classification boundary. The HTTP surface
adds no process execution; its adversarial cases (role spoofing, injection, restricted fields) are already
owned by F-B4's threat model and are covered by the integration suite above.

## Migration / Rollout

No migration. Purely additive; `InMemorySaver` state dies with the process.

## Open Questions

- [ ] Re-confirm `updates` node names/shape at apply time if `langgraph`/`langchain` versions move (the
      design deliberately avoids node-name coupling, but the `jump_to` key detection still touches it).
- [ ] Single-step turns produce one `content` event only; whether re-chunking approved text is worth the
      code is a UX call to settle in tasks.
