"""Tests for app.tools.erp_data / app.tools.erp_seed.

Covers the spec's acceptance criteria: hit/miss lookups, injection-safety of
`order_id`, flat JSON-safe shape, seed idempotency, and LangChain
bindability. All tests run against an isolated tmp_path SQLite database via
the `erp_db` fixture in conftest.py.
"""

import json

from app.tools import get_erp_data
from app.tools.erp_data import _fetch_order
from app.tools.erp_seed import SEED_ORDERS, seed_database


class TestGetErpDataHit:
    def test_returns_seeded_record_with_exact_field_values(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-1001"})

        assert result == {
            "found": True,
            "order_id": "ORD-1001",
            "net_amount": 1000.0,
            "tax_amount": 210.0,
            "total_amount": 1210.0,
            "region": "EU-ES",
            "status": "confirmed",
        }

    def test_tax_mismatch_record_is_returned_unmodified(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-1004"})

        assert result["found"] is True
        assert result["net_amount"] == 1000.0
        assert result["tax_amount"] == 150.0  # not corrected to the 21% rate

    def test_wrong_region_record_is_returned_unmodified(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-1006"})

        assert result["found"] is True
        assert result["region"] == "EU-DE"
        assert result["tax_amount"] == 168.0  # EU-ES-rate tax, EU-DE region

    def test_cancelled_status_is_preserved(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-1008"})

        assert result["found"] is True
        assert result["status"] == "cancelled"

    def test_pending_status_is_preserved(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-1009"})

        assert result["found"] is True
        assert result["status"] == "pending"


class TestGetErpDataMiss:
    def test_unknown_order_id_returns_not_found_without_raising(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-9999"})

        assert result["found"] is False
        assert result["order_id"] == "ORD-9999"
        assert "message" in result


class TestGetErpDataEmptyId:
    def test_empty_string_returns_not_found(self, erp_db):
        result = get_erp_data.invoke({"order_id": ""})

        assert result["found"] is False

    def test_whitespace_only_returns_not_found(self, erp_db):
        result = get_erp_data.invoke({"order_id": "   "})

        assert result["found"] is False


class TestGetErpDataInjectionSafety:
    def test_or_1_equals_1_payload_returns_not_found(self, erp_db):
        payload = "ORD-1001' OR '1'='1"

        result = get_erp_data.invoke({"order_id": payload})

        assert result["found"] is False

    def test_drop_table_comment_payload_returns_not_found(self, erp_db):
        payload = "ORD-1001'; --"

        result = get_erp_data.invoke({"order_id": payload})

        assert result["found"] is False

    def test_table_is_still_queryable_after_injection_attempts(self, erp_db):
        get_erp_data.invoke({"order_id": "ORD-1001' OR '1'='1"})
        get_erp_data.invoke({"order_id": "ORD-1001'; --"})

        # A prior injection attempt must not have dropped the table or
        # returned every row; a normal, legitimate lookup still works.
        result = get_erp_data.invoke({"order_id": "ORD-1001"})
        assert result["found"] is True
        assert result["order_id"] == "ORD-1001"

    def test_injection_payload_never_returns_multiple_rows(self, erp_db):
        # _fetch_order returns a single row (or None) by construction; an
        # `OR '1'='1'`-style payload bound as one literal cannot widen the
        # WHERE clause to match every row.
        order = _fetch_order("ORD-1001' OR '1'='1")

        assert order is None


class TestGetErpDataFlatShape:
    def test_hit_result_has_exact_keys_and_scalar_values(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-1001"})

        assert set(result.keys()) == {
            "found",
            "order_id",
            "net_amount",
            "tax_amount",
            "total_amount",
            "region",
            "status",
        }
        for value in result.values():
            assert isinstance(value, (str, int, float, bool)) or value is None

    def test_hit_result_is_json_serializable(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-1001"})

        assert json.dumps(result)

    def test_miss_result_is_json_serializable(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-9999"})

        assert json.dumps(result)


class TestSeedIdempotency:
    def test_running_seed_database_twice_keeps_row_count_stable(self, erp_db):
        seed_database(erp_db)
        seed_database(erp_db)

        with erp_db.connect() as connection:
            from sqlalchemy import text

            count = connection.execute(
                text("SELECT COUNT(*) FROM erp_orders")
            ).scalar_one()

        assert count == len(SEED_ORDERS)

    def test_running_seed_database_twice_keeps_data_matching_single_run(self, erp_db):
        seed_database(erp_db)
        seed_database(erp_db)

        result = get_erp_data.invoke({"order_id": "ORD-1001"})
        assert result["net_amount"] == 1000.0
        assert result["tax_amount"] == 210.0


class TestGetErpDataToolBindability:
    def test_tool_exposes_name_and_args_schema(self, erp_db):
        assert get_erp_data.name
        assert get_erp_data.args_schema is not None

    def test_tool_invoke_returns_dict_without_error(self, erp_db):
        result = get_erp_data.invoke({"order_id": "ORD-1001"})

        assert isinstance(result, dict)
