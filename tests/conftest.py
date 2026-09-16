"""Shared pytest fixtures.

First test-runner setup for this repo: gives every test function an isolated
SQLite database file under pytest's `tmp_path`, seeded with the mock ERP
dataset, so tests never touch the demo `data/erp_mock.db` file and never leak
state between tests.
"""

import pytest

from app.tools import erp_data


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

    erp_data._reset_engine_cache()
    if db_path.exists():
        db_path.unlink()
