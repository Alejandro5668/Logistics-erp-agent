# Verify Report — F-B5 Agent Core, PR 2 (Integration Tests + README)

**Change**: `f-b5-agent-core`
**Scope**: PR 2 only — task 5.3 (`tests/test_agent_flow.py`, 10 tests) + task 6.1 (`README.md`). PR 1's factory/actions/prompt/test-double are out of scope (already merged and verified separately, `verify-report.md`).
**Branch**: `feature/f-b5-agent-core-integration` (confirmed via `git branch --show-current`).
**Mode**: Full artifacts (spec + design + tasks all present) → completeness, correctness, and design coherence verified.

## Completeness

| Task | Status | Evidence |
|---|---|---|
| 5.3 `tests/test_agent_flow.py` | [x] complete | 10 test classes/methods present, all passing |
| 6.1 `README.md` | [x] complete | AGENT_MODEL, mocked-actions, wiring-only, InMemorySaver sections all present |

No unchecked tasks in PR 2 scope.

## Test Execution Evidence

Command: `pytest -v` (full suite, repo root `C:\Repositorios\Logistics-erp-agent`)

```
274 passed, 1062 warnings in 16.76s
```

Command: `pytest tests/test_agent_flow.py -v` (isolated)

```
10 passed, 358 warnings in 6.07s
```

- 274 total = 264 pre-existing (F-B1–F-B4 + F-B5 PR1) + 10 new PR2 tests. 274 - 10 = 264 matches the expected pre-existing count exactly.
- Zero failures, zero errors. Zero regressions confirmed — all pre-existing tests pass unmodified.

## Genuine-Integration Check (item 1)

- `grep -E "mock|patch|Mock|monkeypatch"` against `tests/test_agent_flow.py`: **no matches**. No mocking of `get_erp_data`, `calculate_tax_discrepancy`, `search_regulations`, or any security function inside the test file itself.
- `erp_db` fixture (`tests/conftest.py`): points `ERP_DB_PATH` at a temp file, calls the real `erp_data._get_engine()` which creates schema + seeds `SEED_ORDERS` — a genuine SQLite engine, not a stub.
- `regulations_index` fixture: points `CHROMA_DB_PATH` at a temp dir, builds a real Chroma collection via `store._get_collection()`. It injects `StubEmbeddingFunction()` in place of Chroma's default ONNX-downloading embedding function — this substitution is pre-existing F-B3 test infrastructure (avoids a network download in CI), not something PR 2 introduced, and it does not touch retrieval/query logic, only vector generation determinism.
- `app/agent/core.py` confirmed: `build_agent()` wires `middleware=[build_security_middleware()]` imported directly from `app.security` (F-B4's real middleware factory) — not a test double.
- Only the chat model is faked (`ScriptedChatModel`, built in PR 1, imported unchanged in PR 2's test file).

**Verdict: genuine integration test confirmed. No tool or guardrail logic mocked or bypassed.**

## Item-by-Item Verification (per orchestrator's 9 focus points)

1. **Genuine integration** — Confirmed above. PASS.
2. **L4 happy-path exact tool order + notify_human never called** — `TestL4HappyPath::test_exact_call_order_and_notify_human_never_called` asserts `_tool_names(...) == ["get_erp_data", "calculate_tax_discrepancy", "search_regulations", "create_erp_adjustment"]` (exact order, list equality) AND a separate explicit `assert "notify_human" not in _tool_names(result["messages"])`. Not merely inferred from create_erp_adjustment being called. PASS.
3. **Both escalation triggers tested independently** — `TestL4EscalationDeltaOutOfRange` (ORD-1004, delta_pct approx -28.57%, outside ±5%, RAG present) and `TestL4EscalationEmptyRag` (ORD-1001, delta_pct == 0 within ±5%, but `search_regulations` queried for year 2099 returns `[]`) are two distinct test classes with distinct scripted sequences and distinct assertions. Both assert `notify_human` called and `create_erp_adjustment` not called. PASS — both policy branches proven independently, not one standing in for the other.
4. **Guardrail-before-model proves model never ran** — `TestL4GuardrailBeforeModel` scripts `ScriptedChatModel(responses=[])` (would raise `AssertionError` on any generate call since exhausted-strict) AND separately asserts `model.index == 0` — a concrete step-count assertion, not just message-content inspection. `_tool_messages(...) == []` confirms zero tool execution too. PASS.
5. **Guardrail-mid-loop proves side effect never happened** — `TestL4GuardrailMidLoop` scripts a `create_erp_adjustment` tool call carrying "salary" in `reason`; asserts `model.index == 1` (model stepped once, proposing the blocked call) and `_tool_messages(result["messages"]) == []` — zero ToolMessages recorded means the ToolNode never executed `create_erp_adjustment`, i.e., no receipt was ever produced. This is a structural proof of "no side effect," not a check on the final message text alone (the final-message assertion is present too, but the empty-ToolMessage-list assertion is the substantive proof). PASS.
6. **Must-not-block uses realistic Spanish text and reaches a real tool call** — `TestL4MustNotBlock` uses `"ajuste por discrepancia de IVA según la normativa 2024"` (realistic Spanish business/fiscal prose, not a crafted token) as the `reason` arg, and asserts the full real chain executes: `_tool_names(...) == ["get_erp_data", "calculate_tax_discrepancy", "search_regulations", "create_erp_adjustment"]` plus `'"status": "simulated"'` in the adjustment tool's real output. PASS.
7. **Memory-continuity proves checkpointer replay concretely** — `TestL4MemoryContinuity` asserts `turn_two_seen_messages = model.seen[-1]` then `assert any(isinstance(m, ToolMessage) for m in turn_two_seen_messages)` — turn 2's model input concretely contains turn 1's `ToolMessage` (not just "test passed"). It also asserts `_tool_names(turn_two["messages"]) == ["get_erp_data"]` — since `turn_two["messages"]` accumulates the full thread history via the checkpointer, `get_erp_data` appearing exactly once across both turns proves the tool was NOT re-invoked in turn 2. PASS.
8. **README accuracy — all four required points**:
   - `AGENT_MODEL` env var: documented in the "Variables de entorno" table (format `provider:model`, default `azure_openai:gpt-4o`, not required for tests). PRESENT.
   - Action tools never mutate state: "Herramientas mockeadas (no mutan estado real)" section states `create_erp_adjustment` never writes to `erp_orders` and `notify_human` never sends a real notification. PRESENT.
   - Test suite is wiring-only, not reasoning-quality proof: "Que prueba la suite de tests (y que no prueba)" section explicitly states it proves cableado (wiring: tool-call order, guardrail interception, memory reuse) and explicitly states it does NOT prove real-LLM reasoning quality, with live-demo verification named as a manual out-of-pytest-scope step. PRESENT.
   - InMemorySaver in-process-only limitation: "Memoria de sesion" section states the default checkpointer is `InMemorySaver`, in-process only, state lost on process restart, no durable persistence (F-B6 deferred). PRESENT.
   All four points present and accurate against actual code (`app/agent/core.py`, `app/tools/actions.py`). PASS.
9. **Zero regressions** — 274 total passed, 264 non-`test_agent_flow.py` tests all passed unmodified (verified via isolated `pytest tests/test_agent_flow.py -v` returning exactly 10, and full-suite 274 total). PASS.

## Spec Compliance Matrix (PR 2 scope)

| Requirement | Scenario | Covering Test | Status |
|---|---|---|---|
| Agent Factory Interface | Default construction wires tools/middleware/checkpointer | (PR 1 — `test_agent_build.py`, out of scope here; `TestL2ZeroTools::test_bound_tools_count_is_five` re-confirms 5 tools bound at integration level) | COMPLIANT (integration re-proof) |
| Model-Agnostic Model Parameter | Fake/stub chat model accepted | All 10 `test_agent_flow.py` tests build via `build_agent(model=ScriptedChatModel(...))` | COMPLIANT |
| Auto-Adjust Decision Policy | Small delta + regulatory backing auto-adjusts | `TestL4HappyPath` | COMPLIANT |
| Escalation Decision Policy | Large delta escalates regardless of RAG | `TestL4EscalationDeltaOutOfRange` | COMPLIANT |
| Escalation Decision Policy | Empty RAG escalates even with small delta | `TestL4EscalationEmptyRag` | COMPLIANT |
| Guardrail Block Ends Run, No Side-Effect | Blocked turn fires no action tool (input side) | `TestL4GuardrailBeforeModel` | COMPLIANT |
| Guardrail Block Ends Run, No Side-Effect | Blocked turn fires no action tool (output/mid-loop side) | `TestL4GuardrailMidLoop` | COMPLIANT |
| Thread-Scoped Session Memory | Second turn reuses resolved tool results | `TestL4MemoryContinuity` | COMPLIANT |
| Offline Test Seam | Fake-model suite runs fully offline | Full suite ran with no `AGENT_MODEL` set, `pytest -v` = 274 passed, 0 network dependency | COMPLIANT |

All PR 2-scoped spec scenarios have a passing covering test at runtime. No CRITICAL gaps found.

## Design Coherence

- `app/agent/core.py` composition matches design.md's `Interfaces / Contracts` block exactly (system_prompt keyword, middleware list, checkpointer default).
- Design's Testing Strategy table (L2/L3/L4 rows) maps 1:1 to the 10 tests present: L2 x2, L3 x1, L4 x7 (happy path, 2 escalation, 2 guardrail, must-not-block, memory).
- Design's "Open Question" on default-construction offline testing is honored: PR 2 tests always inject `ScriptedChatModel`, never exercise the zero-argument credential-requiring path — consistent with the design's documented resolution.
- No design deviations found in PR 2 scope.

## Issues

**CRITICAL**: None.

**WARNING**: None.

**SUGGESTION**:
- None of the `test_agent_flow.py` invocations pass an explicit `context={"role": ...}`, relying on F-B4's fail-closed default role resolution. This is consistent with the spec (role is supplied per-invocation, not bound to the thread) and does not gate PR 2, but a future PR could add one assertion that explicitly varies `role` across turns on the same `thread_id` to more directly prove the "role never bound to session" design guarantee at the integration level (currently only proven at the F-B4 unit-test level in `test_security_middleware.py`).

## Final Verdict

**PASS**

274/274 tests pass (264 pre-existing + 10 new). All 9 orchestrator focus points independently confirmed against actual test code, fixture code, and `app/agent/core.py`/`app/security` wiring. README accurately documents all four required points. Zero regressions. No CRITICAL or WARNING issues found for PR 2 scope.
