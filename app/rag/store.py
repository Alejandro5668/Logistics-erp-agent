"""Regulatory vector-store layer and the LangChain tool adapter.

Two responsibilities live in this file on purpose (see design.md): the Chroma
client/collection/query layer (`_get_client`, `_get_collection`,
`_query_regulations`) and the tool-adapter layer (LLM-facing contract,
`search_regulations`). They change for different reasons, but there is
exactly one collection and one data source, so a full ports-and-adapters
split would be speculative per the architecture-patterns Decision Gates.
"""

from __future__ import annotations

import os
from typing import Optional

from langchain_core.tools import tool

from app.rag.corpus import REGULATION_SNIPPETS, ingest_corpus

DEFAULT_CHROMA_DB_PATH = "data/chroma"
COLLECTION_NAME = "regulations"
N_RESULTS = 3

_client = None
_collection = None
_embedding_function_override = None


def _get_chroma_db_path() -> str:
    """Read the configured Chroma database path, honoring CHROMA_DB_PATH at call time."""
    return os.environ.get("CHROMA_DB_PATH", DEFAULT_CHROMA_DB_PATH)


def _set_embedding_function(embedding_function) -> None:
    """Test-only seam: override the embedding function before the client is built.

    Must be called before `_get_collection()` is first invoked (or after a
    `_reset_store_cache()`), so no test path ever triggers construction of
    the real `DefaultEmbeddingFunction()` (which downloads the ONNX model).
    """
    global _embedding_function_override
    _embedding_function_override = embedding_function


def _resolve_embedding_function():
    """Return the injected override if set, else lazily build the default.

    The override is checked BEFORE `DefaultEmbeddingFunction()` is ever
    constructed, so importing this module or injecting a stub never triggers
    the ONNX model download.
    """
    if _embedding_function_override is not None:
        return _embedding_function_override

    # Imported lazily: constructing DefaultEmbeddingFunction at import time
    # (or before the override check above) would download the ONNX model as
    # a side effect and defeat the test stub.
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    return DefaultEmbeddingFunction()


def _get_client():
    """Lazily build (and cache) the Chroma persistent client.

    Deliberately lazy: building the client at import time would create
    `data/chroma/` as a side effect of importing this module and would
    freeze CHROMA_DB_PATH before tests get a chance to override it.
    """
    global _client
    if _client is None:
        import chromadb

        db_path = _get_chroma_db_path()
        os.makedirs(db_path, exist_ok=True)
        _client = chromadb.PersistentClient(path=db_path)
    return _client


def _get_collection():
    """Lazily build (and cache) the regulations collection.

    Created with `metadata={"hnsw:space": "cosine"}` for a bounded,
    comparable similarity score. On first access, upserts the fixture
    corpus via `ingest_corpus()` so the demo works on a clean checkout.
    """
    global _collection
    if _collection is None:
        client = _get_client()
        embedding_function = _resolve_embedding_function()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=embedding_function,
        )
        ingest_corpus(_collection)
    return _collection


def _reset_store_cache() -> None:
    """Drop the cached client/collection and embedding-function override.

    Test-only escape hatch: tests point CHROMA_DB_PATH at a fresh tmp_path
    per test and must not reuse a previously cached client/collection.

    Also clears Chroma's global system-instance cache
    (`SharedSystemClient.clear_system_cache()`): Chroma caches system
    instances globally by settings, so a second `PersistentClient` at a
    different tmp_path in the same process would otherwise reuse the
    previous test's system — the analogue of F-B1's `engine.dispose()` on
    Windows.
    """
    global _client, _collection, _embedding_function_override
    _client = None
    _collection = None
    _embedding_function_override = None

    # Imported lazily: this is a private API, only needed for test isolation.
    from chromadb.api.client import SharedSystemClient

    SharedSystemClient.clear_system_cache()


def _to_flat_dict(doc_id: str, document: str, metadata: dict, distance: Optional[float]) -> dict:
    """Map one Chroma result row to a flat, JSON-serializable dict.

    `doc_id` comes from the Chroma id and is not duplicated into metadata
    (DRY); `title`/`year`/`source` come from metadata, `text` is the
    document, and `score` is the cosine distance normalized to a bounded,
    comparable similarity value.
    """
    score = round(1 - distance, 4) if distance is not None else None
    return {
        "doc_id": doc_id,
        "title": metadata.get("title"),
        "year": metadata.get("year"),
        "source": metadata.get("source"),
        "text": document,
        "score": score,
    }


def _query_regulations(query: str, year: int) -> list[dict]:
    """Query the regulations collection filtered to an exact-match year.

    The `where={"year": year}` filter is applied *inside* `collection.query()`
    so stale-year noise is excluded by the store, not by post-processing.
    Returns a flat list of dicts, capped at N_RESULTS. Never raises for an
    unmatched year — an empty result is the correct answer.
    """
    collection = _get_collection()
    result = collection.query(
        query_texts=[query],
        n_results=N_RESULTS,
        where={"year": year},
    )

    ids = result["ids"][0] if result["ids"] else []
    documents = result["documents"][0] if result["documents"] else []
    metadatas = result["metadatas"][0] if result["metadatas"] else []
    distances = result["distances"][0] if result.get("distances") else [None] * len(ids)

    return [
        _to_flat_dict(doc_id, document, metadata, distance)
        for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances)
    ]


@tool
def search_regulations(query: str, year: int = 2024) -> list[dict]:
    """Search tax and logistics regulations in force in a given year.

    Use this to justify a tax discrepancy against the rule that applies to the
    invoice's fiscal year. Returns up to 3 regulation snippets from that year only.

    Args:
        query: What to look up, e.g. "tolerancia en discrepancias fiscales".
        year: Fiscal year to filter by. Defaults to 2024.
    """
    return _query_regulations(query, year)


__all__ = [
    "search_regulations",
    "REGULATION_SNIPPETS",
    "DEFAULT_CHROMA_DB_PATH",
    "COLLECTION_NAME",
    "N_RESULTS",
]
