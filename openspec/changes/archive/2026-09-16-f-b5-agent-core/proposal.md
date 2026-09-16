# Proposal: F-B5 — Agent Core (ReAct wiring, action tools, session memory)

## Intent

F-B1..F-B4 are merged and green, but nothing runs them together: there is no object that turns a
natural-language question into tool calls and a decision. F-B5 builds that one `create_agent`
instance — three existing tools plus two new action tools, the F-B4 middleware, and a checkpointer —
so the demo the test asks for (ask → reason → adjust or escalate) exists end to end.

## Scope

### In Scope
- `app/tools/actions.py`: `create_erp_adjustment(order_id, delta, reason)` and
  `notify_human(order_id, reason)` — mocked, deterministic dict results; re-exported from
  `app/tools/__init__.py` (tools stay in the tools package, not `app/agent/`).
- `app/agent/core.py`: `build_agent(model=None, checkpointer=None)` → `create_agent(...)` with the
  5 tools, `middleware=[build_security_middleware()]`, `InMemorySaver`, and a system prompt stating
  the adjust-vs-escalate criteria (agent decides via ReAct; no hand-coded decision branch).
- Model-agnostic: provider-prefixed model string from env (e.g. `AGENT_MODEL=azure_openai:gpt-4o`);
  `model` param is also the test seam (F-B3 `_set_embedding_function` precedent).
- Offline tests: project-owned scripted fake chat model; no network, no credentials.
- `requirements.txt`: explicit `langgraph` (checkpointer import); provider package documented, optional.

### Out of Scope
- FastAPI layer, streaming, HTTP-boundary error handling (F-B6); real Azure deployment (F-A3).
- Real ERP writes — `create_erp_adjustment` MUST NOT mutate `erp_orders`; it returns a simulated receipt.
- Real notification transport; auth (role stays caller-supplied per F-B4's documented limit).
- Any edit to F-B1/F-B2/F-B3/F-B4 logic; retries, Ragas evaluation, persistent checkpointer.

## Capabilities

### New Capabilities
- `agent-orchestration`: agent assembly, tool registry, guardrail wiring, thread-scoped session memory, model swappability.
- `agent-actions`: mocked ERP-adjustment and human-escalation tool contracts.

### Modified Capabilities
- None. F-B1..F-B4 requirements are consumed unchanged.

## Approach

One factory, no custom abstraction over LangChain: `create_agent` already supplies the ReAct loop,
the middleware slot, and the checkpointer. The two action tools follow the merged tool shape
(`@tool`, flat JSON-serializable dict, never raises). Determinism is pushed down — F-B2 computes the
discrepancy, the prompt states the threshold policy, the model only chooses. Tests drive a scripted
fake model so assertions cover wiring (tool order, guardrail blocking, memory reuse), never LLM luck.

## Affected Areas

| Area | Impact | Description |
|------|--------|------------|
| `app/agent/` | New | `build_agent` factory + prompt |
| `app/tools/actions.py` | New | Two mock action tools |
| `app/tools/__init__.py` | Modified | Re-export only |
| `tests/test_agent_*.py` | New | Fake-model integration tests |
| `requirements.txt` | Modified | Add `langgraph` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| First integration of 4 modules — real risk, not routine additive work | High | Integration tests assert the full chain, not per-tool behavior already covered |
| `create_agent` API drift (F-B4 hit exactly this with `AgentMiddleware`) | Med | Verify signature against installed version at design/apply, as F-B3/F-B4 did |
| Guardrail `jump_to: "end"` aborts the whole ReAct run mid-chain | Med | Test a mid-loop block explicitly; document the abort as intended fail-closed |
| Free-text `reason` arg trips F-B4's tool-arg scan, blocking a valid adjustment | Med | Must-not-block test with realistic reason text |
| Fake model proves wiring, not reasoning quality | High (accepted) | State the limit in spec/README; live-LLM check is a manual demo step |
| Checkpointer keyed only by `thread_id` — cross-caller leak if F-B6 reuses ids | Med | Requirement: caller supplies the id; document for F-B6 |

## Rollback Plan

Additive and reversible: delete `app/agent/`, `app/tools/actions.py`, new tests, revert the two
re-export/requirements lines, or drop `feature/f-b5-agent-core`. No schema change, no migration, no
persisted state — `InMemorySaver` dies with the process, and the adjustment tool writes nothing, so
no financial data can be left inconsistent (CLAUDE.md "Superficies sensibles"). Merged F-B1..F-B4
behavior is untouched, so their 228 tests are the regression net.

## Dependencies

- F-B1, F-B2, F-B3, F-B4 — all merged (no open code-level dependency).
- `langgraph` (transitive today, to be pinned explicitly); no live LLM credentials required.

## Success Criteria

- [ ] `build_agent()` returns a runnable agent with 5 tools, guardrail middleware, and a checkpointer.
- [ ] Scripted-model test: ERP lookup → discrepancy → regulation → exactly one action tool.
- [ ] Over-threshold / ambiguous case reaches `notify_human`, not `create_erp_adjustment`.
- [ ] Injection attempt ends the run with the safe message and zero tool calls.
- [ ] Second turn on the same `thread_id` answers without repeating resolved tool calls.
- [ ] Swapping `AGENT_MODEL` changes the provider with no edit to `app/agent/core.py`.
- [ ] `pytest -v` green offline (no network, no API key); existing 228 tests still pass.
