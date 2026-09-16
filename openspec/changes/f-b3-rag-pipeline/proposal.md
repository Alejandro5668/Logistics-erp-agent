# Proposal: F-B3 — Regulatory RAG Pipeline (Chroma + metadata filtering)

## Intent

The agent (F-B5) must justify a tax discrepancy against current regulation, not against a
rule repealed in 2022. The test's rubric grades this explicitly: "índice vectorial simple …
demostrar conocimiento de Metadata Filtering (ej: filtrar documentos solo del año 2024)".
Today there is no retrieval surface at all. F-B3 delivers a small local Chroma index plus a
retrieval tool whose filter is applied **in the query**, so stale-year noise is excluded by
the store, not by post-processing.

## Scope

### In Scope
- `app/rag/`: synthetic normative corpus, index bootstrap/ingestion, retrieval tool.
- ~10 short Spanish normative snippets with metadata (`doc_id`, `title`, `year`, `source`),
  spread across 2022/2023/2024, including **conflicting same-topic rules per year** (e.g. a
  discrepancy tolerance that changed) so the filter is provably doing work.
- `search_regulations(query: str, year: int = 2024)` as a LangChain `@tool`, querying with
  `where={"year": year}` and returning flat, LLM-readable dicts.
- Idempotent ingestion into a persistent collection at a configurable path
  (`CHROMA_DB_PATH`, mirroring F-B1's `ERP_DB_PATH` lazy-init pattern).
- pytest coverage: correct-year hit, cross-year exclusion, empty-result shape.

### Out of Scope
- Real PDF parsing/OCR (mock chunks are explicitly acceptable), re-ranking, hybrid search,
  chunking strategy tuning, Ragas evaluation.
- Agent wiring (F-B5), guardrail (F-B4), API (F-B6).

## Capabilities

### New Capabilities
- `regulatory-retrieval`: year-filtered semantic lookup over normative documents, exposed as an agent tool.

### Modified Capabilities
- None (`erp-data-access` untouched).

## Approach

Thin slice mirroring F-B1: a store layer (`chromadb` persistent client, collection create +
idempotent upsert of the fixture corpus) wrapped by a `@tool` adapter. **Embeddings:** Chroma's
built-in `DefaultEmbeddingFunction` (all-MiniLM-L6-v2 via ONNX) — local, free, no API key, no
torch. It is injectable, so tests pass a deterministic stub and run offline in milliseconds.
Paying for Azure OpenAI embeddings just to index ten fixtures would be speculative cost.

## Affected Areas

| Area | Impact | Description |
|------|--------|------------|
| `app/rag/` | New | Corpus, store bootstrap, `search_regulations` tool |
| `tests/test_rag_*.py` | New | Filter-behavior tests |
| `requirements.txt` | Modified | `chromadb` added |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| First run downloads the ONNX model (network) | Med | Injectable embedding fn; tests never download |
| `chromadb` client API drift (`where` syntax) | Med | Pin a version; assert filter behavior in tests |
| Fixtures too distinct per year → filter looks decorative | Med | Author deliberate cross-year conflicts |

## Rollback Plan

Additive and isolated — no existing code touched. Rollback = delete `app/rag/`, its tests and
`data/chroma/`, revert the `requirements.txt` line, or drop `feature/f-b3-rag-pipeline`.
Nothing imports it until F-B5.

## Dependencies

- `chromadb`. No feature dependencies (parallel with F-B1/F-B2/F-B4).

## Success Criteria

- [ ] Same query returns only 2024 chunks with the default filter, and the superseded 2022 rule when `year=2022`.
- [ ] No document from another year ever appears in a filtered result.
- [ ] Unknown/empty-year query returns a clean empty result, never an exception.
- [ ] `pytest -v` green offline, with a test that fails if the `where` filter is removed.
