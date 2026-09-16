# Design: F-B3 — Regulatory RAG Pipeline (`search_regulations`)

## Technical Approach

Two thin layers, mirroring F-B1 one-for-one (3 responsibilities, 2 modules):

1. **Corpus layer** (`app/rag/corpus.py`) ≙ `erp_seed.py`: the `REGULATION_SNIPPETS` constant
   (~10 Spanish snippets) plus idempotent `ingest_corpus(collection)` using `collection.upsert()`
   (upsert-by-id, the Chroma equivalent of F-B1's `session.merge()`), with a `__main__` entry.
2. **Store + tool layer** (`app/rag/store.py`) ≙ `erp_data.py`: lazy `_get_client()` /
   `_get_collection()` cached at module level, `_query_regulations()`, and below it the
   `@tool search_regulations` adapter owning the LLM-facing docstring and the flat dict mapping.

Per `architecture-patterns` Decision Gates the signals are one data source, no invariants, no
read/write divergence → **plain layered code**, not Hexagonal. A `VectorStorePort` for a single
local Chroma collection is speculative (`solid-principles`: YAGNI/KISS). The split that *is*
justified is SRP: fixture-text changes hit the corpus, client/query changes hit the store, LLM
contract changes hit the tool adapter. Unlike F-B1, no lazy cross-import is needed —
`ingest_corpus` receives the collection as a parameter (DIP), so `corpus.py` imports nothing.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Filtering | `where={"year": year}` passed **into** `collection.query()` | Fetch-then-filter in Python; `$gte/$lte` ranges | The rubric grades store-side filtering; post-filtering silently returns <3 rows and proves nothing. Exact match only — no range, no fallback |
| Unmatched year | Return `[]` | Widen the year; raise | Empty is the correct answer, and the LLM must read the miss, not catch it (F-B1 precedent) |
| Embeddings | `DefaultEmbeddingFunction` (all-MiniLM-L6-v2 / ONNX), **constructed lazily**, override-first | Azure OpenAI embeddings; import-time construction | Local, free, no key, no torch. Eager construction downloads the ONNX model on import and defeats the test stub |
| EF injection seam | Module-level `_embedding_function_override` + `_set_embedding_function(ef)` | Threading a DI parameter through the tool | `@tool` fixes the LLM-facing signature to `(query, year)`; the seam must live beside the cache, like `ERP_DB_PATH`'s |
| Client lifetime | Lazy cached `_get_client()`/`_get_collection()`; `_reset_store_cache()` test hook | Client at import time | Import-time client creates `data/chroma/` as an import side effect and freezes `CHROMA_DB_PATH` before tests set it |
| Distance space | `metadata={"hnsw:space": "cosine"}`; `score = round(1 - distance, 4)` | Default L2; raw distance | Bounded, comparable score; squared-L2 is unreadable to an LLM |
| Ingestion | `collection.upsert()` at first collection access | `add()`; separate migration step | Upsert-by-`doc_id` makes re-runs a no-op; the demo must work on a clean checkout |
| Result shape | Flat `list[dict]`, capped `N_RESULTS = 3` | Nested Chroma response; joined string | Chroma returns list-of-lists (`ids`/`documents`/`metadatas`/`distances`); the LLM gets flat JSON-safe rows |

## Data Flow

    create_agent ──(function call)──> @tool search_regulations(query, year=2024)
                                             │
                                             ▼
                                      _get_collection() ──(first call)──> upsert(REGULATION_SNIPPETS)
                                             │                                   ▲
                                             ▼                                   │
                        collection.query(query_texts=[query],            corpus.py fixture
                                         n_results=3,
                                         where={"year": year})  ──────> Chroma (CHROMA_DB_PATH)
                                             │                              ▲
                                             ▼                    DefaultEmbeddingFunction
                                    flat list[dict] (may be [])   (or injected stub in tests)
                                             │
                                             ▼
                                        LLM context

## File Changes

| File | Action | Description |
|---|---|---|
| `app/rag/__init__.py` | Create | Re-export `search_regulations` (mirrors `app/tools/__init__.py`) |
| `app/rag/corpus.py` | Create | `REGULATION_SNIPPETS` + `ingest_corpus(collection)` + `__main__` |
| `app/rag/store.py` | Create | Lazy client/collection, EF seam, `_query_regulations`, `@tool search_regulations` |
| `tests/embedding_stub.py` | Create | Deterministic offline `StubEmbeddingFunction` |
| `tests/conftest.py` | Modify | Add `regulations_index` fixture (tmp_path + stub EF + cache reset) |
| `tests/test_rag_search.py` | Create | Filter behavior, empty result, shape, bindability |
| `requirements.txt` | Modify | Add pinned `chromadb>=0.5,<0.6` |

`data/` is already gitignored, so `data/chroma/` needs no `.gitignore` change.

## Interfaces / Contracts

```python
DEFAULT_CHROMA_DB_PATH = "data/chroma"
COLLECTION_NAME = "regulations"
N_RESULTS = 3

# corpus.py — one record; `text` is the embedded document, the rest is metadata
{"doc_id": "REG-2024-001", "title": "...", "year": 2024, "source": "...", "text": "..."}

@tool
def search_regulations(query: str, year: int = 2024) -> list[dict]:
    """Search tax and logistics regulations in force in a given year.

    Use this to justify a tax discrepancy against the rule that applies to the
    invoice's fiscal year. Returns up to 3 regulation snippets from that year only.

    Args:
        query: What to look up, e.g. "tolerancia en discrepancias fiscales".
        year: Fiscal year to filter by. Defaults to 2024.
    """
```

Hit row: `{"doc_id": ..., "title": ..., "year": 2024, "source": ..., "text": ..., "score": 0.8123}`.
Miss: `[]` — never an exception. `doc_id` is the Chroma `id`, `title`/`year`/`source` are
metadata, `text` is the document — `doc_id` is not duplicated into metadata (DRY).

## Corpus Design (10 snippets, Spanish)

Grouped into **same-topic / different-year conflicts** so the filter is provably load-bearing:

| Topic | 2022 | 2023 | 2024 |
|---|---|---|---|
| Tolerancia de discrepancia fiscal | `REG-2022-001` — 5% / 50 € | `REG-2023-001` — 2% / 25 € | `REG-2024-001` — 1% / 10 € |
| Tipo impositivo EU-ES | `REG-2022-002` — IVA 21%, sin requisito extra | — | `REG-2024-002` — IVA 21% + justificación documental |
| Tipos regionales EU-DE / LATAM-CO | — | `REG-2023-002` (EU-DE 19%), `REG-2023-003` (LATAM-CO IVA 19%) | `REG-2024-003` — LATAM-CO 19% + retención en la fuente |
| Procedimiento de ajuste | `REG-2022-003` — ajuste automático ≤ 100 € | — | `REG-2024-004` — ajuste automático prohibido, aprobación humana obligatoria |

Distribution: 3 × 2022, 3 × 2023, 4 × 2024. The tolerance row is deliberately near-identical in
wording across the three years and differs only in the number — so an unfiltered query for
"tolerancia" returns a mix of years, and the filtered one cannot.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Correct-year hit | Query "tolerancia en discrepancias fiscales" with default `year=2024` → `REG-2024-001` present, its 1% text returned |
| Unit | **Cross-year exclusion** (the load-bearing test) | Same query with `year=2022` → only `REG-2022-001`; assert every returned `year == requested year` for 2022/2023/2024 |
| Unit | Filter is not decorative | Query the raw collection **without** `where` → assert the top-3 span >1 distinct year; then assert the tool's result spans exactly 1. Fails if `where` is dropped |
| Unit | Empty result | `year=1999` → `== []`, no exception; `query=""` → list, no exception |
| Unit | Shape | Exact key set, scalar values, `json.dumps(result)` does not raise, `len(result) <= 3` |
| Integration | Ingestion idempotency | Run `ingest_corpus()` twice → `collection.count() == len(REGULATION_SNIPPETS)` |
| Integration | Tool bindability | `search_regulations.name` / `.args_schema` exist; `.invoke({"query": ..., "year": ...})` returns a list |

### Offline test isolation (proposal risk: "tests never download")

```python
# tests/embedding_stub.py — deterministic, no model, no network
class StubEmbeddingFunction:           # chromadb duck-types EmbeddingFunction
    def __call__(self, input):         # parameter MUST be named `input` (chromadb validates it)
        return [self._embed(t) for t in input]
    def _embed(self, text):            # hashed bag-of-words -> fixed 64-dim, L2-normalized
        ...                            # sha256(token), NOT built-in hash() (PYTHONHASHSEED-randomized)
```

Hashed bag-of-words keeps lexical similarity real enough that "tolerancia" ranks the tolerance
snippets first, while staying identical across processes and runs.

```python
@pytest.fixture
def regulations_index(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_DB_PATH", str(tmp_path / "chroma"))
    store._reset_store_cache()
    store._set_embedding_function(StubEmbeddingFunction())
    collection = store._get_collection()   # creates + upserts the corpus
    yield collection
    store._reset_store_cache()             # also clears the override
```

`_reset_store_cache()` MUST also call `chromadb.api.client.SharedSystemClient.clear_system_cache()`
(imported lazily): Chroma caches system instances globally by settings, so a second
`PersistentClient` at a different `tmp_path` in the same process would otherwise reuse the
previous test's system — the analogue of F-B1's `engine.dispose()` on Windows. It is a private
API, which is why the `chromadb` pin is load-bearing.

The override is checked **before** `DefaultEmbeddingFunction()` is ever constructed, so no test
path can trigger the ONNX download.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary. The two LLM-controlled inputs are structurally safe: `year` is an
`int` placed into a structured `where` dict (not a query string, no interpolation), and `query`
is passed as a `query_texts` value that Chroma only embeds. No user text reaches a SQL string,
a path, or a shell.

## Migration / Rollout

No migration required. The collection is created and upserted on first access; the store lives
under `CHROMA_DB_PATH` (default `data/chroma`), which is disposable and already gitignored.
Rollback per the proposal: delete `app/rag/`, its tests, `data/chroma/`, and the
`requirements.txt` line. Nothing imports it until F-B5.

## Open Questions

- [ ] None blocking. The `chromadb` version must be pinned during apply and the two
      version-sensitive surfaces re-confirmed against it: `metadata={"hnsw:space": "cosine"}`
      at collection creation, and `SharedSystemClient.clear_system_cache()`. If either has
      drifted in the installed version, fix the pin — do not work around it in application code.
- [ ] Snippet wording (title/source strings) is authored at apply time; only the year/topic
      conflict matrix above is contractual.
