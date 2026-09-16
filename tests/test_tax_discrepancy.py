"""Tests for app.tools.tax_discrepancy.

Covers the spec's acceptance criteria: anti-drift against F-B1's seeded
rates, both call modes, signed deltas, the cent-level tolerance boundary,
and every readable-failure shape (unknown region, invalid input) with no
exception ever escaping the core arithmetic. Tests exercise the tool via
`.invoke()` (the agent-facing contract) except where pydantic's own
float-coercion at the `.invoke()` boundary would pre-empt the business
validation under test (non-numeric `amount`/`reported_tax`); those use
`.func()` to reach `_calculate_discrepancy` directly, matching the design's
"no exception may escape the core" guarantee rather than LangChain's own
schema-coercion behavior.

Pure function, no fixtures, no I/O — no `erp_db` needed.
"""

import json

import pytest

from app.tools.erp_seed import SEED_ORDERS
from app.tools.tax_discrepancy import REGION_TAX_RATES, calculate_tax_discrepancy


def _seed_order(order_id: str) -> dict:
    """Look up a single seeded order by id (test helper, not a fixture)."""
    for order in SEED_ORDERS:
        if order["order_id"] == order_id:
            return order
    raise KeyError(order_id)


class TestTaxDiscrepancyAntiDrift:
    """Locks REGION_TAX_RATES to F-B1's seeded, already-clean orders.

    Fails if either side drifts: the rate table or the seeded amounts.
    """

    @pytest.mark.parametrize("order_id", ["ORD-1001", "ORD-1002", "ORD-1003"])
    def test_clean_seed_order_matches_with_zero_delta(self, order_id):
        order = _seed_order(order_id)

        result = calculate_tax_discrepancy.invoke(
            {
                "amount": float(order["net_amount"]),
                "region": order["region"],
                "reported_tax": float(order["tax_amount"]),
            }
        )

        assert result["match"] is True
        assert result["delta"] == 0.0
        assert result["expected_tax"] == float(order["tax_amount"])


class TestTaxDiscrepancyDeltas:
    def test_ord_1004_under_tax_has_negative_delta(self):
        order = _seed_order("ORD-1004")

        result = calculate_tax_discrepancy.invoke(
            {
                "amount": float(order["net_amount"]),
                "region": order["region"],
                "reported_tax": float(order["tax_amount"]),
            }
        )

        assert result["delta"] == -60.0
        assert result["match"] is False

    def test_ord_1005_over_tax_has_positive_delta(self):
        order = _seed_order("ORD-1005")

        result = calculate_tax_discrepancy.invoke(
            {
                "amount": float(order["net_amount"]),
                "region": order["region"],
                "reported_tax": float(order["tax_amount"]),
            }
        )

        assert result["delta"] == 60.0
        assert result["match"] is False


class TestTaxDiscrepancyWrongRegion:
    """ORD-1006/1007: tax matches a *different* region's rate.

    Arithmetic still reports the correct signed delta against the *stated*
    region; naming the other, better-fitting region is F-B5's reasoning,
    out of scope for this pure arithmetic tool (design.md Decision 6).
    """

    @pytest.mark.parametrize("order_id", ["ORD-1006", "ORD-1007"])
    def test_reports_signed_delta_against_stated_region_only(self, order_id):
        order = _seed_order(order_id)
        expected_tax = round(
            float(order["net_amount"]) * float(REGION_TAX_RATES[order["region"]]), 2
        )

        result = calculate_tax_discrepancy.invoke(
            {
                "amount": float(order["net_amount"]),
                "region": order["region"],
                "reported_tax": float(order["tax_amount"]),
            }
        )

        assert result["region"] == order["region"]
        assert result["expected_tax"] == expected_tax
        assert result["match"] is False
        assert "inferred_region" not in result
        assert set(result.keys()) == {
            "known_region",
            "valid_input",
            "region",
            "amount",
            "tax_rate",
            "expected_tax",
            "reported_tax",
            "delta",
            "delta_pct",
            "match",
        }


class TestTaxDiscrepancyModeA:
    def test_expected_tax_only_when_reported_tax_omitted(self):
        result = calculate_tax_discrepancy.invoke({"amount": 1000.00, "region": "EU-ES"})

        assert result == {
            "known_region": True,
            "valid_input": True,
            "region": "EU-ES",
            "amount": 1000.0,
            "tax_rate": 0.21,
            "expected_tax": 210.0,
        }
        assert "delta" not in result
        assert "match" not in result
        assert "reported_tax" not in result


class TestTaxDiscrepancyTolerance:
    @pytest.mark.parametrize(
        ("reported_tax", "expected_match"),
        [
            (210.009, True),
            (210.010, False),
            (209.991, True),
            (209.990, False),
        ],
    )
    def test_boundary_around_cent_level_tolerance(self, reported_tax, expected_match):
        result = calculate_tax_discrepancy.invoke(
            {"amount": 1000.00, "region": "EU-ES", "reported_tax": reported_tax}
        )

        assert result["match"] is expected_match

    def test_reported_tax_within_float_noise_tolerance_matches(self):
        result = calculate_tax_discrepancy.invoke(
            {"amount": 1000.00, "region": "EU-ES", "reported_tax": 210.004999}
        )

        assert result["match"] is True

    def test_reported_tax_one_cent_beyond_tolerance_is_mismatch(self):
        result = calculate_tax_discrepancy.invoke(
            {"amount": 1000.00, "region": "EU-ES", "reported_tax": 210.02}
        )

        assert result["match"] is False
        assert result["delta"] == 0.02


class TestTaxDiscrepancyUnknownRegion:
    def test_unknown_region_mode_a_returns_known_region_false_no_exception(self):
        result = calculate_tax_discrepancy.invoke({"amount": 1000.00, "region": "APAC-JP"})

        assert result["known_region"] is False
        assert "expected_tax" not in result
        assert "APAC-JP" in result["message"]
        assert "EU-DE" in result["message"]
        assert "EU-ES" in result["message"]
        assert "LATAM-CO" in result["message"]

    def test_unknown_region_full_verdict_mode_returns_known_region_false(self):
        result = calculate_tax_discrepancy.invoke(
            {"amount": 1000.00, "region": "APAC-JP", "reported_tax": 190.00}
        )

        assert result["known_region"] is False
        assert "match" not in result
        assert "delta" not in result

    def test_empty_region_is_unknown(self):
        result = calculate_tax_discrepancy.invoke({"amount": 1000.00, "region": ""})

        assert result["known_region"] is False

    def test_lowercase_region_is_normalized_and_still_known(self):
        # design.md: region input is `.strip().upper()`-normalized before the
        # lookup, specifically for robustness against a case mismatch like
        # "eu-es" — this must resolve, not report an unknown region.
        result = calculate_tax_discrepancy.invoke({"amount": 1000.00, "region": "eu-es"})

        assert result["known_region"] is True
        assert result["region"] == "EU-ES"


class TestTaxDiscrepancyInvalidInput:
    @pytest.mark.parametrize("bad_amount", [-5, "abc", float("nan"), float("inf")])
    def test_invalid_amount_returns_valid_input_false_no_exception(self, bad_amount):
        result = calculate_tax_discrepancy.func(bad_amount, "EU-ES")

        assert result["known_region"] is True
        assert result["valid_input"] is False
        assert "amount" in result["message"]

    def test_amount_zero_is_valid_not_invalid(self):
        result = calculate_tax_discrepancy.invoke({"amount": 0.0, "region": "EU-ES"})

        assert result["valid_input"] is True
        assert result["expected_tax"] == 0.0

    @pytest.mark.parametrize("bad_reported_tax", [-1, "xyz", float("nan"), float("inf")])
    def test_invalid_reported_tax_returns_valid_input_false_no_exception(self, bad_reported_tax):
        result = calculate_tax_discrepancy.func(1000.00, "EU-ES", bad_reported_tax)

        assert result["known_region"] is True
        assert result["valid_input"] is False
        assert "reported_tax" in result["message"]

    def test_no_exception_escapes_for_combined_garbage_input(self):
        try:
            calculate_tax_discrepancy.func("garbage", "nowhere")
        except Exception as exc:  # pragma: no cover - defensive, must not trigger
            pytest.fail(f"calculate_tax_discrepancy raised unexpectedly: {exc}")


class TestTaxDiscrepancyShapeSerialization:
    def test_shape_a_expected_only_is_json_serializable_scalars_only(self):
        result = calculate_tax_discrepancy.invoke({"amount": 1000.00, "region": "EU-ES"})

        assert json.dumps(result)
        for value in result.values():
            assert isinstance(value, (str, int, float, bool)) or value is None

    def test_shape_b_full_verdict_is_json_serializable_scalars_only(self):
        result = calculate_tax_discrepancy.invoke(
            {"amount": 1000.00, "region": "EU-ES", "reported_tax": 150.00}
        )

        assert json.dumps(result)
        for value in result.values():
            assert isinstance(value, (str, int, float, bool)) or value is None

    def test_shape_c_unknown_region_is_json_serializable(self):
        result = calculate_tax_discrepancy.invoke({"amount": 1000.00, "region": "APAC-JP"})

        assert json.dumps(result)

    def test_shape_d_invalid_input_is_json_serializable(self):
        result = calculate_tax_discrepancy.func(-5, "EU-ES")

        assert json.dumps(result)


class TestTaxDiscrepancyToolBindability:
    def test_tool_exposes_name_and_args_schema(self):
        assert calculate_tax_discrepancy.name == "calculate_tax_discrepancy"
        assert calculate_tax_discrepancy.args_schema is not None

    def test_tool_invoke_matches_core_result(self):
        invoked = calculate_tax_discrepancy.invoke(
            {"amount": 1000.00, "region": "EU-ES", "reported_tax": 150.00}
        )
        core = calculate_tax_discrepancy.func(1000.00, "EU-ES", 150.00)

        assert invoked == core
