"""Shared pytest fixtures.

First test-runner setup for this repo: gives every test function an isolated
SQLite database file under pytest's `tmp_path`, seeded with the mock ERP
dataset, so tests never touch the demo `data/erp_mock.db` file and never leak
state between tests.
"""

import pytest

from app.rag import store
from app.tools import erp_data
from tests.embedding_stub import StubEmbeddingFunction


@pytest.fixture
def erp_db(tmp_path, monkeypatch):
    """Point ERP_DB_PATH at a temporary database, seeded and isolated per test.

    Resets erp_data's cached engine/session before and after the test so the
    lazy `_get_engine()` picks up the temporary path instead of a stale
    cached engine from a previous test or from the module's default.
    """
    db_path = tmp_path / "erp_mock_test.db"
    monkeypatch.setenv("ERP_DB_PATH", str(db_path))

    erp_data._reset_engine_cache()
    engine = erp_data._get_engine()  # creates schema + seeds SEED_ORDERS

    yield engine

    engine.dispose()  # release the SQLite file handle before cleanup (Windows)
    erp_data._reset_engine_cache()
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def regulations_index(tmp_path, monkeypatch):
    """Point CHROMA_DB_PATH at a temporary Chroma store, isolated per test.

    Resets store's cached client/collection before and after the test (via
    `_reset_store_cache()`, which also clears Chroma's global system-instance
    cache) so the lazy `_get_collection()` picks up the temporary path and a
    fresh client instead of a previous test's cached one. Injects the
    deterministic `StubEmbeddingFunction` before the collection is ever
    built, so no test path triggers the real `DefaultEmbeddingFunction()`
    ONNX download.
    """
    db_path = tmp_path / "chroma"
    monkeypatch.setenv("CHROMA_DB_PATH", str(db_path))

    store._reset_store_cache()
    store._set_embedding_function(StubEmbeddingFunction())
    collection = store._get_collection()  # creates + upserts REGULATION_SNIPPETS

    yield collection

    store._reset_store_cache()  # also clears the embedding-function override
