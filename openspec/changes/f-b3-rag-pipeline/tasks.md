# Tasks: F-B3 — Regulatory RAG Pipeline (Chroma + Metadata Filtering)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 380–565 (authored code + tests) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR (`feature/f-b3-rag-pipeline`) |
| Delivery strategy | single-pr |
| Chain strategy | N/A — preflight approved single PR |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception (preflight approved single PR, manageable scope)
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Complete RAG pipeline (all 7 files) + comprehensive tests | PR 1 (single, `feature/f-b3-rag-pipeline`) | `pytest -v tests/test_rag_search.py` | `python app/rag/corpus.py` (seeds collection); `pytest -v --cov=app` (full verify) | Delete `app/rag/`, `tests/test_rag_search.py`, `tests/embedding_stub.py`, revert `conftest.py` and `requirements.txt` |

---

## Phase 1: Dependencies and Test Utilities

- [ ] 1.1 Add `chromadb>=0.5,<0.6` to `requirements.txt`
  - Spec link: Required for Chroma vector store (proposal, approach)
  - Line count: 1 line added
  - Completion check: Pin in file, version constraint documented

- [ ] 1.2 Create `tests/embedding_stub.py` with `StubEmbeddingFunction` class
  - Spec link: Required for offline, deterministic tests (design: Offline test isolation)
  - Implements hashed bag-of-words (SHA256) → 64-dim L2-normalized vectors
  - `__call__(input)` returns `[self._embed(t) for t in input]` (Chroma duck-type signature)
  - `_embed(text)` hashes tokens (not PYTHONHASHSEED-randomized), preserves lexical similarity ("tolerancia" ranks tolerance snippets first)
  - Line count: ~40–60 lines
  - Completion check: Stub is importable, deterministic, no network access, compatible with conftest fixture setup

---

## Phase 2: Core Implementation

- [ ] 2.1 Create `app/rag/corpus.py` with regulatory snippets and idempotent ingestion
  - Spec link: Required for "Idempotent Ingestion" scenario (spec R4)
  - Define `REGULATION_SNIPPETS` list: ~10 Spanish snippets (3×2022, 3×2023, 4×2024)
  - Intentional cross-year conflicts (tolerance rule differs by %, topic is identical) so filter proves load-bearing
  - Record format: `{"doc_id": "REG-YYYY-NNN", "title": "...", "year": YYYY, "source": "...", "text": "..."}`
  - Implement `ingest_corpus(collection)` using `collection.upsert(ids=[...], documents=[...], metadatas=[...])` (upsert-by-id, no duplicates on re-run)
  - Add `if __name__ == "__main__"` entry point: `get_collection()` + `ingest_corpus(collection)` for manual seeding
  - Line count: ~50–80 lines
  - Completion check: Fixture validates 10 snippets, years distributed as specified, `__main__` is runnable, corpus imports nothing (DIP)

- [ ] 2.2 Create `app/rag/store.py` with lazy client, collection, EF injection, and @tool adapter
  - Spec link: Required for tool interface (spec R1), metadata filter (spec R2), empty result (spec R3), flat shape (spec R5), tool bindability (spec R1 scenario 2)
  - Constants: `DEFAULT_CHROMA_DB_PATH = "data/chroma"`, `COLLECTION_NAME = "regulations"`, `N_RESULTS = 3`
  - Implement `_embedding_function_override = None`, `_set_embedding_function(ef)` (seam for test injection)
  - Implement `_get_client()` (lazy cached `chromadb.PersistentClient(path=CHROMA_DB_PATH)`, call once per test isolation boundary)
  - Implement `_get_collection()` (lazy cached, creates with `metadata={"hnsw:space": "cosine"}` for bounded score normalization, first call upserts `REGULATION_SNIPPETS`)
  - Implement `_reset_store_cache()` (clears module-level cache, calls `chromadb.api.client.SharedSystemClient.clear_system_cache()` to prevent Chroma global reuse across tests)
  - Implement `_query_regulations(query: str, year: int) -> list[dict]` (calls `collection.query(query_texts=[query], n_results=N_RESULTS, where={"year": year})`, transforms nested Chroma response to flat list of dicts)
  - Implement `@tool search_regulations(query: str, year: int = 2024)` with LLM-facing docstring ("Search tax and logistics regulations…"), calls `_query_regulations`, returns flat list, capped at 3 results
  - Transform Chroma response `{"ids": [...], "documents": [...], "metadatas": [...], "distances": [...]}` to `list[{"doc_id": id, "title": ..., "year": ..., "source": ..., "text": doc, "score": round(1 - dist, 4)}]`
  - Line count: ~120–150 lines
  - Completion check: Lazy loading verified (no client created on import), EF override checked before `DefaultEmbeddingFunction()` instantiation, `@tool` attributes exist (name, args_schema), empty query returns `[]`, cosine distance normalized to 0–1 range

- [ ] 2.3 Create `app/rag/__init__.py` to re-export `search_regulations`
  - Spec link: Required for tool bindability (spec R1)
  - Import `from app.rag.store import search_regulations` and add to `__all__`
  - Mirror pattern from `app/tools/__init__.py`
  - Line count: ~5 lines
  - Completion check: Tool is importable from `app.rag`, docstring preserved

---

## Phase 3: Testing Infrastructure

- [ ] 3.1 Modify `tests/conftest.py` to add `regulations_index` fixture
  - Spec link: Required for all test scenarios (spec R1–R5)
  - Create fixture `regulations_index(tmp_path, monkeypatch)` that:
    - Sets `CHROMA_DB_PATH` environment variable to `str(tmp_path / "chroma")`
    - Calls `store._reset_store_cache()` to clear module state
    - Injects `StubEmbeddingFunction()` via `store._set_embedding_function()`
    - Calls `store._get_collection()` (creates collection + upserts `REGULATION_SNIPPETS`)
    - Yields the collection for test use
    - Cleans up: calls `store._reset_store_cache()` after test
  - Line count: ~15–25 lines
  - Completion check: Fixture is scoped to function (default), no persistent test data leaks, stub EF is active during tests

---

## Phase 4: Integration Tests

- [ ] 4.1 Create `tests/test_rag_search.py` with comprehensive test suite (all spec scenarios)
  - Spec link: Tests cover all spec requirements (R1–R5) and design testing strategy
  
  **Correct-year hit (spec R2 scenario 1):**
  - [ ] 4.1.1 Test `search_regulations("tolerancia en discrepancias fiscales", year=2024)` returns `REG-2024-001` with correct 1% text
  - Verify exact `year == 2024`, title matches, text is readable
  
  **Cross-year exclusion (spec R2 scenario 2, design: load-bearing test):**
  - [ ] 4.1.2 Test same query `year=2022` returns only `REG-2022-001` with 5% text
  - Verify all returned docs have `year == 2022`
  
  - [ ] 4.1.3 Test same query `year=2023` returns only `REG-2023-001` with 2% text
  - Verify all returned docs have `year == 2023`
  
  **Filter is not decorative (design: test approach):**
  - [ ] 4.1.4 Test raw collection query (without `where` filter) returns top-3 spanning multiple years
  - Query directly via collection (bypass tool), assert >1 distinct year in top-3
  - Then test tool result spans exactly 1 year (filter is active)
  - Fails if `where` clause is removed or forgotten
  
  **Empty-result behavior (spec R3):**
  - [ ] 4.1.5 Test `search_regulations(query, year=1999)` returns `[]`, no exception
  - Verify type is list, length is 0
  
  - [ ] 4.1.6 Test `search_regulations("", year=2024)` returns list (may be empty), no exception
  - Empty query must not raise
  
  **Result shape (spec R5):**
  - [ ] 4.1.7 Test result shape: verify each dict has exactly keys `{"doc_id", "title", "year", "source", "text", "score"}`
  - Verify all values are scalars (no nested lists/dicts)
  - Verify `json.dumps(result)` succeeds (JSON-serializable)
  - Verify `len(result) <= 3`
  - Line count: ~150–200 lines for 7 test cases
  
  **Ingestion idempotency (spec R4, design testing strategy):**
  - [ ] 4.1.8 Test run `corpus.ingest_corpus(collection)` twice, assert `collection.count() == len(REGULATION_SNIPPETS)`
  - Verify no duplicate `doc_id` entries
  
  **Tool bindability (spec R1 scenario 2, design testing strategy):**
  - [ ] 4.1.9 Test `search_regulations.name` exists (string), `.args_schema` exists
  - Test `.invoke({"query": "...", "year": 2024})` returns a list
  - Verify default `year=2024` works when year is omitted from `.invoke()` call
  
  - Line count: ~150–200 lines (all test cases combined)
  - Completion check: All 9 sub-tests pass, no external network calls, `pytest -v tests/test_rag_search.py` shows 9 passing tests

- [ ] 4.2 Run full test suite and verify coverage
  - Command: `pytest -v tests/test_rag_search.py`
  - Verify all 9 test scenarios pass (correct-year hit, 3×cross-year exclusion, filter not decorative, 2×empty result, shape, idempotency, bindability)
  - Run `python app/rag/corpus.py` to verify manual seeding works (creates `data/chroma/` if not present)
  - Optionally run `pytest -v --cov=app` to measure coverage (note: coverage_threshold is 0 in config, but verify no major gaps)
  - Line count: 0 lines (execution task)
  - Completion check: All tests pass, corpus seeding succeeds, no exceptions

---

## Phase 5: Cleanup and Verification

- [ ] 5.1 Verify requirements.txt pin does not introduce conflicts
  - Run `pip install -e .` (or install from `requirements.txt`)
  - Verify no version conflicts with existing deps (LangChain, FastAPI, SQLAlchemy, pytest, etc.)
  - Line count: 0 lines (verification task)
  - Completion check: Installation succeeds, no deprecation warnings for Chroma

- [ ] 5.2 Final integration check: Run full test suite
  - Command: `pytest -v --cov=app`
  - Verify all tests pass (new RAG tests + any existing tests)
  - Verify no import errors in `app/rag/` or `app/tools/` (exports)
  - Line count: 0 lines (verification task)
  - Completion check: Full test suite passes, no regressions

---

## Notes

- **No threat matrix**: Design specifies N/A — no routing, shell, subprocess, VCS boundary, or process-integration. Inputs are structurally safe (year is int in dict, query is embedded text only).
- **No migrations**: Collection is created and upserted on first access; `data/chroma/` is disposable and already gitignored.
- **Rollback boundary**: Delete `app/rag/`, `tests/test_rag_search.py`, `tests/embedding_stub.py`, conftest fixture, revert `requirements.txt`. Nothing imports it until F-B5.
- **Parallel readiness**: F-B3 can run in parallel with F-B1, F-B2, F-B4 per project config. No cross-feature dependencies.
- **Reference**: This change mirrors F-B1's thin-slice pattern (corpus fixtures + store layer + tool adapter), adapted for vector retrieval.
