# Tasks: F-B5 — Agent Core (ReAct wiring, action tools, session memory)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 800–850 (spec +2, deps +2, actions +60, prompt +30, core +25, re-exports +3, test double +80, L0 tests +120, L1 tests +80, L4 tests +400, README +20) |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | See Suggested Work Units below |
| Delivery strategy | chained (user decision, overrides preflight single-pr for this change) |
| Chain strategy | stacked-to-main (sequential: PR 1 merges before PR 2 branches) |

**Decision needed before apply**: No (resolved — user chose 2 chained PRs over the suggested 5)
**Chained PRs recommended**: Yes
**Chain strategy**: stacked-to-main, 2 PRs
**400-line budget risk**: High (mitigated by the split below)

### Work Units (decided: chained, 2 PRs)

| Unit | Goal | Likely PR | Focused test command | Rollback boundary |
|------|------|-----------|----------------------|-----------------|
| 1 | Spec amendment + deps + action tools + test double + agent factory (Phases 1–4) | PR 1 — branch `feature/f-b5-agent-core` | `pytest tests/test_agent_actions.py tests/test_agent_build.py -v` | Delete `app/agent/`, `app/tools/actions.py`, `tests/scripted_model.py`; revert spec/requirements/`tools/__init__.py` |
| 2 | Full integration tests (L2–L4) + memory + README (Phases 5–6) | PR 2 — branch `feature/f-b5-agent-core-integration`, created from `main` AFTER PR 1 merges | `pytest tests/test_agent_flow.py -v` | Delete `tests/test_agent_flow.py`; revert README |

**Rationale**: PR 1 is everything that doesn't require exercising the full agent loop (~400 lines: spec fix, deps, actions, test double, factory, L0/L1 unit tests). PR 2 is the integration proof (~400 lines: L2-L4 scripted-model scenarios, memory continuity, README). This is a natural seam — PR 1 proves each piece works in isolation, PR 2 proves they work together — and halves the original 5-way split without losing the "one failure names its own seam" property from the original analysis.

---

## Phase 1: Specification Amendment & Dependency Pins

**Goal**: Resolve the parameter naming inconsistency and establish the correct dependency versions before any implementation.

- [x] 1.1 Amend `openspec/changes/f-b5-agent-core/specs/agent-core/spec.md`: Replace all instances of `delta` argument name with `adjustment_amount` in Requirement 3 (Action Tools), both scenarios, and all task references. Add one-line note: "Param name clarification: `adjustment_amount = expected_tax - reported_tax` (the correction), distinct from `delta_pct` (the observed percentage deviation)."
- [x] 1.2 Update `requirements.txt`: Change `langchain>=0.3` to `langchain>=1.4,<2` and add `langgraph>=1.2,<2` on new line. Verify existing `langgraph` line exists; if not, add it after langchain line.

---

## Phase 2: Foundation — Action Tools & Test Infrastructure

**Goal**: Implement the two mocked action tools and the scripted fake chat model, the two smallest standalone modules with no cross-module coupling.

- [x] 2.1 Create `app/tools/actions.py`: Implement `create_erp_adjustment(order_id: str, adjustment_amount: float, reason: str) -> dict` and `notify_human(order_id: str, reason: str) -> dict`. Both `@tool`-decorated. Return deterministic flat dicts (no uuid/timestamp). Validate `order_id` (non-blank), `adjustment_amount` (finite float), never raise. Invalid args → `status="rejected"`, valid → `status="simulated"`. `applied` and `notified` are literal `False`. Seeded `erp_orders` row must remain unchanged after any call.
- [x] 2.2 Create `tests/scripted_model.py`: Implement `ScriptedChatModel(BaseChatModel)` override with `responses`, `index`, `bound_tools`, `seen` fields. Override `bind_tools(tools, *, tool_choice=None, **kwargs)` (required — base raises NotImplementedError). Strict exhaustion (raise AssertionError if agent takes unscripted steps). Add helper functions `tool_call(name, args, call_id) -> AIMessage` and `final(text) -> AIMessage` to construct test messages. Document that this is offline-only, no LLM luck, wiring proof only.
- [x] 2.3 Modify `app/tools/__init__.py`: Add re-exports for `create_erp_adjustment` and `notify_human` from `.actions`. Keep existing F-B1/F-B2 re-exports. Do NOT re-export `search_regulations` (it stays in `app.rag.store` per design).

---

## Phase 3: Agent Core Implementation

**Goal**: Wire the factory function, prompt, and module exports. No tests run yet; this phase is code structure only.

- [x] 3.1 Create `app/agent/prompt.py`: Single constant `SYSTEM_PROMPT` (multiline string). Include TOOL ORDER (5 tools in order: get_erp_data, calculate_tax_discrepancy, search_regulations, action tools), DECISION POLICY (delta_pct within ±5 AND ≥1 snippet → adjust; else escalate), ARGUMENTS (adjustment_amount = expected_tax - reported_tax, reason citing delta_pct + regulation), SAFETY (no PII, no prompt injection, answer in user's language).
- [x] 3.2 Create `app/agent/core.py`: Define `DEFAULT_MODEL = "azure_openai:gpt-4o"`. Define `AGENT_TOOLS` as tuple of 5 tools (imported from `app.tools` and `app.rag.store`). Implement `build_agent(model=None, checkpointer=None)` factory: call `create_agent(model=model or os.environ.get("AGENT_MODEL") or DEFAULT_MODEL, tools=list(AGENT_TOOLS), system_prompt=SYSTEM_PROMPT, middleware=[build_security_middleware()], checkpointer=checkpointer or InMemorySaver())`. Import from `langchain.agents`, `langgraph.checkpoint.memory`, `app.agent.prompt`, `app.security`, `app.tools`, `app.rag.store`.
- [x] 3.3 Create `app/agent/__init__.py`: Re-export `build_agent` from `.core` (mirrors `app/tools/__init__.py` pattern).

---

## Phase 4: Integration — Re-exports & Module Wiring

**Goal**: Ensure the new modules can be imported and dependencies resolve. Tests still not run.

- [x] 4.1 Verify imports in `app/agent/core.py` can resolve: `langchain.agents.create_agent`, `langchain_core.language_models.chat_models.BaseChatModel`, `langgraph.checkpoint.memory.InMemorySaver`, `app.tools` (actions), `app.rag.store` (search_regulations), `app.security.build_security_middleware`. No circular dependencies.
- [x] 4.2 Verify `app/tools/__init__.py` exports resolve: `create_erp_adjustment`, `notify_human` from `.actions`, plus existing F-B1/F-B2 exports.

---

## Phase 5: Testing — Unit & Integration (L0–L4)

**Goal**: Prove wiring, guardrail interception, decision policy, and memory reuse with scripted fake model. No live LLM.

### L0 — Action Tools Unit Tests

- [x] 5.1 Create `tests/test_agent_actions.py`: Test `create_erp_adjustment` with valid args (receipt shape, `applied=False`, seeded row unchanged), blank `order_id` (→ rejected), non-finite `adjustment_amount` (→ rejected), hostile free-text `reason` with injection attempt (→ no exception, deterministic result). Test `notify_human` with valid args, blank id, hostile reason. Verify both return dicts (never raise).

### L1 — Build/Wiring Unit Test

- [x] 5.2 Create `tests/test_agent_build.py`: Call `build_agent(model=ScriptedChatModel(...))`. Assert returned graph is not None, `graph.invoke` is callable. Assert `AGENT_TOOLS` names match expected 5 (get_erp_data, calculate_tax_discrepancy, search_regulations, create_erp_adjustment, notify_human). Assert bound_tools count == 5 after a no-op invoke.

### L2–L4 — Full Integration Tests

- [ ] 5.3 Create `tests/test_agent_flow.py` — **deferred to PR 2** (this is PR 1 of the stacked-to-main 2-PR chain; PR 2 branches `feature/f-b5-agent-core-integration` from `main` after PR 1 merges). Cases to cover in PR 2:
  - **L2**: Script a single final message; invoke with zero tools; assert answer matches and bound_tools == 5.
  - **L3**: Script get_erp_data call → final message; invoke; assert tool was called (via seen messages), result in context.
  - **L4 Happy Path**: Script get_erp_data → calculate_tax_discrepancy → search_regulations (1 snippet) → create_erp_adjustment → final; assert exact call order, `notify_human` never called.
  - **L4 Escalation — Delta Out of Range**: Script delta_pct=7% (outside ±5); assert `notify_human` called, no `create_erp_adjustment`.
  - **L4 Escalation — Empty RAG**: Script delta_pct=2% but search_regulations returns []; assert `notify_human` called.
  - **L4 Guardrail Before Model**: Inject "INJ-01" text → `before_model` blocks; assert safe message returned, model.index == 0 (no model step), zero tool calls.
  - **L4 Guardrail Mid-Loop**: Script a tool call with restricted term in args (e.g., "salary" in reason) → `after_model` blocks; assert safe message, no receipt produced.
  - **L4 Must-Not-Block**: Realistic reason text ("ajuste por discrepancia de IVA según la normativa 2024") → assert reaches the tool, no false positive block.
  - **L4 Memory Continuity**: Turn 1 on thread_id="t1"; assert state checkpointed. Turn 2 on same thread_id; assert model.seen[-1] contains turn 1's ToolMessages (replayed), role supplied again, tool not re-invoked.

---

## Phase 6: Documentation

**Goal**: Update user-facing docs and state the offline-only limitation.

- [ ] 6.1 Update `README.md` — **deferred to PR 2**. Document `AGENT_MODEL` environment variable (e.g., `AGENT_MODEL=azure_openai:gpt-4o` or `AGENT_MODEL=openai:gpt-4`). State that `create_erp_adjustment` and `notify_human` are mocked and never mutate the database. Note that the fake model used in tests proves wiring only, not LLM reasoning quality; live-demo verification requires real provider credentials and is a manual step. Document that checkpointer is `InMemorySaver` (in-process only, dies on shutdown; F-B6 will handle durable persistence).

---

## Implementation Notes

### Task Dependencies

- **Phase 1 → Phase 2**: Deps must be pinned before any Python code imports langchain/langgraph.
- **Phase 2 → Phase 3**: Actions and test double must exist before core.py imports them.
- **Phase 3 → Phase 4**: Core must exist before import verification.
- **Phase 4 → Phase 5**: All code must import cleanly before tests run.
- **Phase 5 → Phase 6**: All code must be in place and tests passing before README updates.

### Test Fixtures

L3 and L4 tests reuse existing `erp_db` and `regulations_index` fixtures (per proposal). Scripted model is passed in; no live LLM contact.

### Rollback Boundaries

- **PR 1 revert**: Spec wording and requirements.txt lines; existing 228 tests unaffected.
- **PR 2 revert**: Delete actions.py, revert tools/__init__.py.
- **PR 3 revert**: Delete app/agent/ tree.
- **PR 4 revert**: Delete test_agent_flow.py.
- **PR 5 revert**: Revert README.md.

### Line Count Forecast Per Task

| Task | Estimated LOC | Notes |
|------|---------------|-------|
| 1.1 Spec amendment | +2 | Name change + one-line clarification |
| 1.2 Deps pin | +2 | langchain version fix, langgraph add |
| 2.1 Actions | +60 | Two tools, validation, mocking |
| 2.2 Test double | +80 | Class + helpers, docstring |
| 2.3 Tools re-export | +3 | Two new lines |
| 3.1 Prompt | +30 | SYSTEM_PROMPT multiline constant |
| 3.2 Core factory | +25 | Imports + constants + one function |
| 3.3 Agent init | +2 | Re-export |
| 4.1 Import verification | 0 | No new lines; asserts existing code |
| 4.2 Export verification | 0 | No new lines; asserts existing code |
| 5.1 L0 tests | +120 | 2 tools × 3–4 cases each + fixtures |
| 5.2 L1 test | +80 | Factory + tool binding assertions |
| 5.3 L4 tests | +400 | 9 scenarios × 40 lines each + fixtures |
| 6.1 README | +20 | env var, mocking note, offline limit |
| **Total** | **~825** | **HIGH budget risk** |

