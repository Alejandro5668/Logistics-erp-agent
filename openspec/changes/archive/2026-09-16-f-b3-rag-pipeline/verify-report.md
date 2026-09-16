# Verification Report: f-b3-rag-pipeline

**Change**: F-B3 -- Regulatory RAG Pipeline (search_regulations)
**Mode**: Full artifact verification (proposal + specs + design + tasks all present)
**Branch**: feature/f-b3-rag-pipeline (worktree C:\Repositorios\Logistics-erp-agent-f-b3)
**Verdict**: PASS WITH WARNINGS

---

## 1. Task Completeness

All 16 tasks in tasks.md are checked [x] across Phases 1-5 (dependencies/test utilities, core implementation, testing infrastructure, integration tests, cleanup/verification). No unchecked tasks. Task claims were cross-checked against actual code, not taken at face value -- see sections 2-4.

## 2. Test Execution Evidence

Command: pytest -v (full suite, run from C:\Repositorios\Logistics-erp-agent-f-b3)

Result: 35 passed, 704 warnings in 4.22s

- 19 pre-existing tests in tests/test_erp_data.py (F-B1) -- all pass, no regression.
- 16 new tests in tests/test_rag_search.py (F-B3) -- all pass.
- Exit code 0. Warnings are Pydantic deprecation noise from chromadb's internal types.py, unrelated to this change, not actionable.

Matches the apply report's claimed 35/35 (19 + 16). Verified by direct re-run, not by trusting the apply claim.

## 3. Spec Compliance Matrix

| Requirement | Scenario | Covering Test | Result |
|---|---|---|---|
| Tool Interface and Bindability | Bindable with default year | TestSearchRegulationsToolBindability::test_tool_exposes_name_and_args_schema, test_tool_invoke_with_default_year_returns_list | PASS |
| Tool Interface and Bindability | Accepts explicit year override | TestSearchRegulationsCrossYearExclusion::test_year_2023_returns_only_2023_tolerance_snippet (year=2023 explicit) | PASS |
| Metadata-Filter Correctness | Only requested year returned | TestSearchRegulationsCrossYearExclusion::test_year_2024_excludes_every_other_year | PASS |
| Metadata-Filter Correctness | Same-topic different-year excluded | TestSearchRegulationsCrossYearExclusion (all three year variants assert all(row["year"] == requested)) + TestFilterIsNotDecorative | PASS |
| Empty-Result Behavior | Year with no matching chunks | TestSearchRegulationsEmptyResult::test_unmatched_year_returns_empty_list_without_raising (year=1999, spec example uses 2099 -- semantically equivalent, both years absent from the 10-snippet corpus) | PASS |
| Idempotent Ingestion | Re-running ingestion twice | TestIngestionIdempotency::test_running_ingest_corpus_twice_keeps_count_stable, test_running_ingest_corpus_twice_keeps_no_duplicate_doc_ids | PASS |
| Flat Result Shape | Capped flat dicts, exact keys | TestSearchRegulationsFlatShape (3 tests: exact keys/scalars, JSON-serializable, capped at 3) | PASS |

All 5 spec requirements / 7 scenarios have a passing runtime-covering test. No CRITICAL UNTESTED/FAILING findings.

### Load-bearing test: filter is not decorative

TestFilterIsNotDecorative:
- test_unfiltered_query_spans_more_than_one_year: queries the raw collection directly (bypassing the tool, no where clause) for "tolerancia de discrepancia fiscal", asserts the top-3 result spans more than one distinct year. Verified passing -- confirms the corpus's cross-year conflict design actually produces topically-close, differently-dated matches under the stub embedding.
- test_tool_filtered_result_spans_exactly_one_year: same query through the search_regulations tool with year=2024, asserts result years equal exactly {2024}. Verified passing.

This pair is genuinely load-bearing: if where={"year": year} were ever dropped from store.py::_query_regulations, the second test would start returning multiple years and fail, while the first test's assertion (no filter, must span >1 year) would remain true -- so the pair only passes when the filter is real and active, not decorative. Confirmed by reading store.py lines 152-156: where={"year": year} is passed directly into collection.query(), not applied as a post-filter.

### Empty-result / no-fallback behavior

Confirmed in store.py::_query_regulations (lines 143-166): the function performs exactly one collection.query() call with the exact-match where clause and returns whatever Chroma returns -- zero widening, zero retry with a different year, zero exception handling that would mask a genuine miss. test_unmatched_year_returns_empty_list_without_raising (year=1999, absent from the 10-snippet corpus spanning 2022-2024) confirms an empty list is returned with no exception. Design's explicit rejection of "widen the year" or "raise" is honored in the actual code, not just documented.

## 4. Design Coherence

All 8 design decisions in design.md's Architecture Decisions table were checked against code:

| Decision | Code Location | Match |
|---|---|---|
| where= passed into collection.query() | store.py:152-156 | Yes |
| Unmatched year returns [] | store.py:143-166 (no fallback branch) | Yes |
| DefaultEmbeddingFunction, lazy, override-first | store.py:45-60 (_resolve_embedding_function, override checked before import) | Yes |
| EF injection seam (module-level override + setter) | store.py:26,34-42 | Yes |
| Lazy cached client/collection + _reset_store_cache() | store.py:63-97,100-121 | Yes |
| metadata={"hnsw:space": "cosine"}; score = round(1-distance,4) | store.py:93,132 | Yes |
| collection.upsert() idempotent ingestion | corpus.py:132-154 | Yes |
| Flat list[dict], N_RESULTS = 3 | store.py:22,124-140,163-166 | Yes |

File Changes table (7 files) matches exactly what was delivered: app/rag/__init__.py, app/rag/corpus.py, app/rag/store.py, tests/embedding_stub.py, tests/conftest.py (modified), tests/test_rag_search.py, requirements.txt (modified). Corpus distribution (3x2022, 3x2023, 4x2024, 10 total) matches corpus.py exactly, including the deliberate same-topic/different-year conflict structure (tolerance rule, EU-ES rate, regional rates, adjustment procedure).

No design deviations found beyond the two explicitly documented ones (reviewed below).
## 5. Review of Documented Deviations

### Deviation 1 -- Test query wording: plural to singular

Apply changed the test query from the design snippet's illustrative "tolerancia en discrepancias fiscales" to "tolerancia de discrepancia fiscal" (singular, matching the corpus's exact wording), because StubEmbeddingFunction does bag-of-words hashing with no stemming -- plural tokens (discrepancias, fiscales) hash to different buckets than the corpus's singular tokens (discrepancia, fiscal), which would silently starve the cosine-similarity signal the load-bearing test depends on.

Assessment: sound, not a shortcut. Confirmed by reading embedding_stub.py: _embed() does raw text.lower().split() with no lemmatization/stemming (lines 41-61), so this is a real, mechanical limitation of the stub, not a convenience excuse. The design's own snippet (design.md line 84) is illustrative LLM-facing docstring text, not a contractual test fixture; the design's own corpus rows also all use the singular "tolerancia de discrepancia fiscal" wording (see design.md's Corpus Design table, row 1, and corpus.py's literal text). What the load-bearing test actually proves -- that where={"year": year} is real and not decorative -- is orthogonal to which exact query string is used, as long as (a) the query is topically close to all three years' tolerance snippets under the embedding function in use, and (b) test_unfiltered_query_spans_more_than_one_year independently proves that closeness holds (it does -- verified passing). Switching to the corpus's own vocabulary does not weaken this: it is the correct fix for a deterministic-stub limitation, not a weakening of the assertion being tested. The docstring-facing plural phrasing ("tolerancia en discrepancias fiscales") is preserved in store.py's tool docstring (line 177) for the LLM-facing contract -- only the test query was changed, not the production-facing example text. No spec or design requirement pins the literal test query string; this is implementation-detail latitude explicitly left open by design.md's own Open Questions section ("Snippet wording ... is authored at apply time").

### Deviation 2 -- Hardcoded Spanish stopword list in the test stub

StubEmbeddingFunction._embed() filters a fixed set of ~25 high-frequency Spanish function words before hashing tokens, added because shared grammar words were dominating cosine similarity over topical content words, which would have made the load-bearing filter test's premise (topically-close, differently-dated snippets) unreliable.

Assessment: sound, additive test-infrastructure only. Confirmed by reading: _STOPWORDS is defined and used exclusively in tests/embedding_stub.py (lines 27-30, 49). store.py's production embedding path (_resolve_embedding_function, lines 45-60) only ever imports and constructs chromadb.utils.embedding_functions.DefaultEmbeddingFunction -- a real ONNX sentence-transformer with no dependency on, or awareness of, this stopword list. The two code paths do not share any code or data; the stopword list cannot influence production retrieval quality, precision, or ranking. This is a legitimate deterministic-test-fixture engineering choice (feature-hashing bag-of-words is a coarse approximation of semantic similarity, and without stopword removal, shared grammar words across all 10 Spanish snippets would swamp the topical signal -- a well-known bag-of-words weakness, not unique to this codebase). design.md's own stub sketch (lines 122-133) was explicitly non-final pseudocode, so this is filling in an implementation detail left open by design, not deviating from a specified algorithm.

Conclusion on both deviations: neither weakens spec compliance, neither touches the production code path, and both are documented with clear technical rationale grounded in the actual limitations of the deterministic stub. Sound engineering judgment, not shortcuts.
## 6. Flagged Risk (RESOLVED) -- requirements.txt chromadb pin

**Status**: RESOLVED — chromadb==0.5.4 exact pin now present in requirements.txt with explanatory comment.

requirements.txt now correctly reads:

chromadb==0.5.4  # pinned exact: newer 0.5.x releases have no prebuilt chroma-hnswlib wheel for Windows/cp312, forcing an MSVC build

The apply phase reported it had to manually resolve to chromadb==0.5.4 specifically on this Windows environment due to wheel availability constraints. The verify phase originally flagged this as a WARNING because requirements.txt at that time expressed an open range (>=0.5,<0.6) instead of the exact pin. That warning is now resolved: the exact pin has been committed to the main branch (PR #3 for feature/f-b3-rag-pipeline merged to main). The installed version in the final merged state matches the pin exactly.

This confirms reproducibility is secured: any future pip install -r requirements.txt on a clean Windows machine will install the exact chromadb==0.5.4 version that shipped with this feature, preventing the silent build-failure gap.

## 7. Issues Summary

### CRITICAL
None.

### WARNING
None. (The chromadb pinning warning from initial verification has been resolved in the merged code.)

### SUGGESTION
1. tasks.md task 4.1/4.2 completion notes reference "9 test scenarios" / "9 sub-tests" as the target count; the delivered tests/test_rag_search.py actually contains 16 individual test methods (more granular than the 9 named scenario groups in the task description, not fewer -- no coverage gap). Cosmetic mismatch between planning-doc phrasing and delivered test count; no action required, noted for task-doc accuracy only.
2. tests/test_rag_search.py uses year=1999 for the "no matching chunks" case where the spec's illustrative scenario uses year=2099; both are semantically equivalent (any year absent from the 10-snippet 2022-2024 corpus). No action required.

## 8. Final Verdict

PASS WITH WARNINGS (now PASS — all warnings resolved in merged PR)

- 35/35 tests passing (19 F-B1 regression + 16 new F-B3), confirmed by direct execution, not by trusting the apply report.
- All 5 spec requirements / 7 scenarios have passing runtime-covering tests.
- All 8 design architecture decisions verified against actual code.
- All 16 tasks verified complete and consistent with delivered code.
- Both documented deviations reviewed and confirmed to be sound, well-reasoned engineering judgment addressing real limitations of the deterministic test stub -- neither weakens spec compliance nor touches the production embedding path.
- The requirements.txt chromadb pinning warning has been resolved in the merged code: exact pin chromadb==0.5.4 is now committed with explanatory comment.

Safe to archive. All critical and blocking issues resolved.
