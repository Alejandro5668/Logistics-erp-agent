# Archive Report: F-B5 — Agent Core (ReAct wiring, action tools, session memory)

**Archived**: 2026-09-16  
**Change**: `f-b5-agent-core`  
**Status**: COMPLETE — Two chained PRs delivered, merged to main, all tests passing  
**Final Test Count**: 274/274 passing (264 pre-existing + 10 new PR2)

## Summary

F-B5 Agent Core is the integration point wiring F-B1 through F-B4 into one `create_agent` ReAct instance with thread-scoped session memory. The change was delivered across two sequential pull requests (PR 1: Phases 1–4 + L0/L1 tests; PR 2: L2–L4 integration tests + README), both merged to main, with zero CRITICAL or WARNING issues across all verification stages. All 26/26 implementation tasks completed and marked in the persisted tasks artifact.

## Delivery Strategy

**Chained PRs (stacked-to-main)**: Two work units, each with autonomous scope, clear rollback boundary, and independent verification.

- **PR 1** (`feature/f-b5-agent-core` → main): Spec amendment + dependencies + action tools + test double + agent factory + L0/L1 unit tests (36 new tests, 228 pre-existing green)
- **PR 2** (`feature/f-b5-agent-core-integration` → main): Full L2–L4 integration tests + README (10 new tests, 264 pre-existing green)

Both PRs merged as-is on 2026-09-16 (end of session date). No fixes, rework, or follow-ups required after PR 1 merged.

## Completeness (Task Completion Gate)

All implementation tasks marked complete in persisted `tasks.md`:

| Phase | Task Count | Status |
|-------|-----------|--------|
| 1: Spec Amendment & Deps | 2/2 | ✓ Complete |
| 2: Action Tools & Test Double | 3/3 | ✓ Complete |
| 3: Agent Core Implementation | 3/3 | ✓ Complete |
| 4: Re-exports & Wiring | 2/2 | ✓ Complete |
| 5: Testing (L0–L4) | 3/3 | ✓ Complete |
| 6: Documentation | 1/1 | ✓ Complete |
| **TOTAL** | **26/26** | ✓ Complete |

No stale unchecked tasks. Task artifact accurately reflects final code state.

## Verification Status (Native Review Authority)

### PR 1 Verification (Phases 1–4 + L0/L1 tests)

**Verdict**: PASS  
**Evidence**: Per `openspec/changes/archive/2026-09-16-f-b5-agent-core/verify-report.md`  
**Test Results**: 264/264 passing (228 pre-existing + 36 new)  
**Critical Issues**: 0  
**Warnings**: 0  
**Suggestions**: 1 (design.md checkbox staleness — non-blocking)

**Targeted Attention Items Confirmed**:
1. requirements.txt pin fix — CONFIRMED (langchain>=1.4,<2; langgraph>=1.2,<2 added) — prior broken pin had no `create_agent`/`AgentMiddleware` exports
2. No ERP mutation — CONFIRMED (app/tools/actions.py is pure dict construction; before/after snapshot test asserts seeded row unchanged)
3. ScriptedChatModel correctness — CONFIRMED (`bind_tools` override present, strict exhaustion via AssertionError, no silent cycling)
4. build_agent() exact signature — CONFIRMED (system_prompt=SYSTEM_PROMPT, middleware=[build_security_middleware()], checkpointer=InMemorySaver())
5. Checkpointer not singleton — CONFIRMED (InMemorySaver() created fresh per call)
6. SYSTEM_PROMPT legibility — CONFIRMED (decision policy stated as prose: delta_pct ±5 AND ≥1 snippet → adjust; else escalate)
7. 228 pre-existing tests unmodified — CONFIRMED (git diff shows no pre-existing test touched)
8. .func() testing pattern consistency — CONFIRMED (mirrors existing F-B2 convention)

### PR 2 Verification (L2–L4 integration tests + README)

**Verdict**: PASS  
**Evidence**: Per `openspec/changes/archive/2026-09-16-f-b5-agent-core/verify-report-pr2.md`  
**Test Results**: 274/274 passing (264 pre-existing + 10 new)  
**Critical Issues**: 0  
**Warnings**: 0  
**Suggestions**: 1 (future PR could add explicit role-variation test)

**Orchestrator Focus Points Independently Confirmed**:
1. Genuine integration — CONFIRMED (no tool/guardrail mocks; real erp_db, regulations_index fixtures; F-B4's real middleware)
2. L4 happy-path exact tool order — CONFIRMED (assert _tool_names == ["get_erp_data", "calculate_tax_discrepancy", "search_regulations", "create_erp_adjustment"] and notify_human not called)
3. Both escalation triggers tested independently — CONFIRMED (delta out of range; empty RAG — both tested separately)
4. Guardrail-before-model — CONFIRMED (model.index == 0, zero tool calls)
5. Guardrail-mid-loop — CONFIRMED (model.index == 1, zero ToolMessages recorded)
6. Must-not-block with realistic Spanish text — CONFIRMED (full chain executes, no false positive)
7. Memory continuity / checkpointer replay — CONFIRMED (turn 2 sees turn 1's ToolMessages, tool not re-invoked)
8. README accuracy — CONFIRMED (AGENT_MODEL env var, mocked actions, wiring-only proof, InMemorySaver limitation all documented)
9. Zero regressions — CONFIRMED (274 total passed, 264 non-test_agent_flow tests unmodified)

## Spec & Design Coherence

**Spec Compliance**: All requirements and scenarios met at runtime.  
**Design Decisions**: All architecture decisions honored (plain layered composition, AGENT_TOOLS tuple, system_prompt keyword, prose decision policy, per-call InMemorySaver, distinct adjustment_amount vs delta_pct naming).

**API Drift Risk Mitigated**: Design verified against langchain==1.4.0 and langgraph==1.2.11 API facts before implementation.

**Open Questions Status**:
- [x] Spec wording (adjustment_amount) — RESOLVED in PR 1, task 1.1
- [ ] Default construction offline test — Design documents limitation; zero-argument path requires credentials (design resolution honored: tests inject ScriptedChatModel)
- [ ] Provider package declaration — Stays optional; documented in README as live-demo prerequisite

## Final Code State

**Main Specs Synced**: New spec merged into openspec/specs/agent-core/spec.md (delta spec copied; no main spec existed to merge into).

**Change Folder Archived**: All artifacts moved from `openspec/changes/f-b5-agent-core/` to `openspec/changes/archive/2026-09-16-f-b5-agent-core/` with the following contents:

- `proposal.md` — Intent, scope, approach, risks, rollback plan
- `design.md` — Technical approach, architecture decisions, verified API facts, file changes, testing strategy
- `tasks.md` — All 26/26 tasks (6 phases, L0–L4 testing, README)
- `verify-report.md` — PR 1 verification (PASS, 264 tests, 0 CRITICAL)
- `verify-report-pr2.md` — PR 2 verification (PASS, 274 tests, 0 CRITICAL)
- `specs/agent-core/spec.md` — Agent Core specification (8 requirements, scenarios, delta_pct policy, wiring limits)

**Repository State at Archive Time**: main branch has both PRs merged; 274 tests green. git log shows PR #6 and PR #7 merged in order.

## Risk Summary

**No CRITICAL or WARNING issues** from either verification report. The one SUGGESTION in PR 1 (design.md checklist staleness) is documentation-only, non-blocking, and does not affect code, tests, or spec.

**Integration risk mitigated**: Tests proved wiring (tool order, guardrail blocking, memory reuse) with scripted fake model offline. All 4 integrated modules (F-B1/F-B2/F-B3/F-B4) run real code; only LLM is faked. Fallback to manual live-demo for LLM reasoning quality (out of pytest scope, documented in README).

**Design decisions risk mitigated**: API facts verified against installed versions; langchain/langgraph version pins correct. Per-call InMemorySaver default avoids cross-test/cross-caller leaks. Distinct adjustment_amount naming prevents model conflation.

## Next Steps

This change is **complete and closed**. No follow-up tasks, open items, or blocked work units remain.

- F-B6 (FastAPI integration, durable persistence, streaming) can proceed independently.
- Live-LLM demo requires manual credential setup and provider package installation (outside SDD scope; documented in README).

## Archive Metadata

**Archived Artifacts**:
- `openspec/specs/agent-core/spec.md` (main spec, new capability)
- `openspec/changes/archive/2026-09-16-f-b5-agent-core/` (all change artifacts)

**Verification Basis**:
- Both verify reports: PASS with 0 CRITICAL issues
- Task completion: 26/26 tasks checked
- Test count: 274/274 passing (final state per main branch)
- No stale unchecked implementation tasks

**Session**: SDD archive phase for `f-b5-agent-core`, completed 2026-09-16.

---

## Document History

| Date | Event | Details |
|------|-------|---------|
| 2026-09-15 | f-b5-agent-core proposal | Initiated SDD cycle |
| 2026-09-16 | PR 1 applied & verified | Phases 1–4, L0/L1 tests (264 green) |
| 2026-09-16 | PR 2 applied & verified | L2–L4 tests, README (274 green) |
| 2026-09-16 | Main branch merged | Both PRs integrated, no conflicts |
| 2026-09-16 | SDD archive | All artifacts moved to archive, spec synced to main |

**Status**: DELIVERED AND ARCHIVED — ready for next change.
