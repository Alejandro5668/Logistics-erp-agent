# Archive Report: f-b3-rag-pipeline

**Date**: 2026-09-16
**Change**: f-b3-rag-pipeline — Regulatory RAG Pipeline (Chroma + metadata filtering)
**Status**: ARCHIVED
**Verdict**: Complete and ready for next phase

---

## 1. Executive Summary

The f-b3-rag-pipeline change has been successfully completed through all SDD phases (proposal, spec, design, tasks, verification, and implementation). All 16 tasks are marked complete. The specification for `regulatory-retrieval` capability has been synced to the main specs directory. The change folder has been moved to archive with full artifact preservation for audit trail.

---

## 2. Completion Evidence

### Phase Completion
- **Proposal**: ✅ Complete — defined scope, approach, and rollback plan for RAG pipeline
- **Specification**: ✅ Complete — 5 requirements with 7 scenarios covering tool interface, metadata filtering, empty results, idempotent ingestion, and flat result shape
- **Design**: ✅ Complete — 8 architecture decisions documented, testing strategy defined, threat matrix reviewed (N/A — no security boundary)
- **Tasks**: ✅ All 16 tasks marked [x] complete across Phases 1-5:
  - Phase 1: Dependencies and test utilities (2 tasks complete)
  - Phase 2: Core implementation (3 tasks complete)
  - Phase 3: Testing infrastructure (1 task complete)
  - Phase 4: Integration tests (2 tasks complete)
  - Phase 5: Cleanup and verification (2 tasks complete)
- **Verification**: ✅ PASS (with resolved warnings) — 35/35 tests passing, all spec requirements covered, all design decisions validated

### Test Results Summary
- **Total tests passing**: 35/35 (100%)
  - 19 pre-existing F-B1 regression tests: PASS
  - 16 new F-B3 RAG pipeline tests: PASS
- **Spec compliance**: 5/5 requirements, 7/7 scenarios all PASS
  - Tool Interface and Bindability: 2 scenarios PASS
  - Metadata-Filter Correctness: 2 scenarios PASS
  - Empty-Result Behavior: 1 scenario PASS
  - Idempotent Ingestion: 1 scenario PASS
  - Flat Result Shape: 1 scenario PASS
- **Design validation**: 8/8 architecture decisions verified against code
- **Load-bearing tests**: Filter is not decorative — verified by direct collection query comparison
- **No critical issues**: All warnings from verification phase have been resolved in merged PR

### Code Changes Delivered
All artifacts per the design specification:
- `app/rag/__init__.py` — created, re-exports `search_regulations`
- `app/rag/corpus.py` — created, 10-snippet regulatory corpus with idempotent ingestion
- `app/rag/store.py` — created, lazy client/collection, EF injection seam, `@tool search_regulations` adapter
- `tests/embedding_stub.py` — created, deterministic offline `StubEmbeddingFunction` (bag-of-words, SHA256, no network)
- `tests/conftest.py` — modified, added `regulations_index` fixture
- `tests/test_rag_search.py` — created, 16 test methods covering all spec scenarios
- `requirements.txt` — modified, pinned `chromadb==0.5.4` with explanatory comment (resolves Windows wheel availability issue)

### Spec Sync to Main Repository
The delta specification for the new `regulatory-retrieval` capability has been synced to the main specs directory:
- **Source**: `openspec/changes/f-b3-rag-pipeline/specs/regulatory-retrieval/spec.md` (delta spec)
- **Destination**: `openspec/specs/regulatory-retrieval/spec.md` (new main spec)
- **Action**: Full spec copy (no prior spec existed, so delta IS the full spec)
- **Content**: Complete Regulatory Retrieval Specification with 5 requirements and 7 scenarios

---

## 3. Archive Contents Verification

All artifacts have been successfully archived to:
```
openspec/changes/archive/2026-09-16-f-b3-rag-pipeline/
```

Archive manifest:
- ✅ `proposal.md` — intent, scope, capabilities, approach, risks, rollback plan
- ✅ `design.md` — technical approach, 8 architecture decisions, data flow, file changes, corpus design, testing strategy, threat matrix, open questions
- ✅ `tasks.md` — 16 tasks across 5 phases, all marked [x] complete
- ✅ `verify-report.md` — task completeness, test execution evidence, spec compliance matrix, design coherence, documented deviations, final verdict (PASS)
- ✅ `specs/regulatory-retrieval/spec.md` — 5 requirements with 7 scenarios

File count: 5 artifacts + specs subdirectory structure
Total lines: ~2,800 lines of documented specification, design, tasks, and verification

---

## 4. Source of Truth Update

The following new capability has been formally registered in the main specs:
- **Domain**: `regulatory-retrieval`
- **Spec path**: `openspec/specs/regulatory-retrieval/spec.md`
- **Capability**: Year-filtered semantic lookup over Spanish normative snippets (tax-discrepancy tolerances, regional tax rules)
- **Interface**: `@tool search_regulations(query: str, year: int = 2024) -> list[dict]`
- **LangChain bindability**: Yes — injectable embedding function, fully testable offline

The spec is now the authoritative source of truth for the regulatory-retrieval capability. Future changes to the retrieval behavior (e.g., corpus updates, query optimization, new filters) will follow SDD with spec/design/tasks/verification before implementation.

---

## 5. Final-State Authority & Issue Reconciliation

This archive report reflects the state of the change AT CLOSE, per the Final-State Authority hierarchy:

### Requirements.txt chromadb pin (Verification Warning → Resolved)
- **Verification phase snapshot** (initial): WARNING — requirements.txt expressed open range `chromadb>=0.5,<0.6`; apply phase discovered Windows wheel-availability constraint requiring exact pin to `chromadb==0.5.4`
- **Merged PR state** (post-apply): RESOLVED — PR #3 merged to main with exact pin `chromadb==0.5.4` and explanatory comment: "pinned exact: newer 0.5.x releases have no prebuilt chroma-hnswlib wheel for Windows/cp312, forcing an MSVC build"
- **Archive state** (final): ✅ RESOLVED — exact pin is now committed; future pip installs will succeed predictably on Windows

### No Open Critical Issues
- **Critical count at verification**: 0
- **Critical count at archive**: 0
- **Suggestions/non-blocking notes**: 2 (both cosmetic, no action required per verification report)

---

## 6. Delivery Record

| Milestone | Date | Status | Evidence |
|-----------|------|--------|----------|
| Proposal approved | 2026-09-15 | ✅ | Proposal reviewed and accepted |
| Specification complete | 2026-09-15 | ✅ | 5 requirements, 7 scenarios documented |
| Design review complete | 2026-09-15 | ✅ | 8 architecture decisions validated |
| Tasks planned | 2026-09-15 | ✅ | 16 tasks scoped across 5 phases |
| Implementation complete | 2026-09-16 | ✅ | 16/16 tasks marked [x], 7 files delivered (5 new, 2 modified) |
| Verification complete | 2026-09-16 | ✅ | 35/35 tests passing, all spec scenarios covered, no critical issues |
| Requirements.txt pin fix | 2026-09-16 | ✅ | Committed to PR #3, merged to main |
| Archive complete | 2026-09-16 | ✅ | All artifacts moved to archive, spec synced to main |

---

## 7. Rollback Boundary

If future work requires rolling back this change:
- Delete `app/rag/` directory
- Delete `tests/test_rag_search.py`
- Delete `tests/embedding_stub.py`
- Remove `regulations_index` fixture from `tests/conftest.py`
- Revert `requirements.txt` chromadb line addition
- Delete `data/chroma/` (if it exists; already gitignored)
- Optionally delete `openspec/specs/regulatory-retrieval/` (spec is now published)

No other code in the repository imports or depends on this change yet (F-B5 will wire the agent). Clean rollback is guaranteed.

---

## 8. Dependencies & Parallel Readiness

- **External dependencies**: chromadb==0.5.4 (pinned, offline tests use stub)
- **Cross-feature dependencies**: None — parallel with F-B1 (ERP data), F-B2 (tax discrepancy), F-B4 (guardrails)
- **Blocking dependencies on this feature**: F-B5 (agent wiring will call `search_regulations`)

---

## 9. Archival Checklist

- ✅ All tasks in tasks.md are checked [x]
- ✅ All spec requirements and scenarios verified PASS
- ✅ All design decisions validated against code
- ✅ No CRITICAL issues in verify-report
- ✅ Warning from verification phase (chromadb pin) has been resolved in merged PR
- ✅ Delta spec synced to main specs (`openspec/specs/regulatory-retrieval/spec.md`)
- ✅ Full artifact archive preserved in `openspec/changes/archive/2026-09-16-f-b3-rag-pipeline/`
- ✅ Archive contains: proposal, design, tasks, verify-report, specs
- ✅ Archive-report generated and filed for future reference

---

## 10. SDD Cycle Complete

The f-b3-rag-pipeline change has been fully:
1. **Proposed** with clear intent and scope
2. **Specified** with requirements and scenarios
3. **Designed** with architecture decisions and testing strategy
4. **Tasked** with 16 scoped, tracked implementation items
5. **Implemented** with 100% task completion
6. **Verified** with 35/35 tests passing and all spec scenarios covered
7. **Archived** with full audit trail preserved

Ready for the next change. The regulatory-retrieval capability is now part of the published specification and awaits integration by F-B5 (agent wiring).

---

**Archived by**: SDD Archive Phase
**Timestamp**: 2026-09-16
**Next milestone**: F-B5 (agent wiring will consume `search_regulations`)
