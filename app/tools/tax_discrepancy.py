"""Deterministic tax-discrepancy logic for logistics orders.

Pure-Python expected-tax lookup and invoice-vs-expected deviation verdict for
a seeded region rate table, exposed as a LangChain tool so F-B5's
adjustment/escalation choice never depends on LLM arithmetic (see
design.md). `REGION_TAX_RATES` is pinned to F-B1's seeded data in
`app/tools/erp_seed.py` and locked by the anti-drift test in
`tests/test_tax_discrepancy.py`.

Money is `Decimal` end-to-end (rates as `Decimal`, products quantized to 2
decimals `ROUND_HALF_UP`); `float()` is used only when building the returned,
JSON-serializable dict.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from langchain_core.tools import tool

REGION_TAX_RATES: dict[str, Decimal] = {
    "EU-ES": Decimal("0.21"),
    "EU-DE": Decimal("0.19"),
    "LATAM-CO": Decimal("0.19"),
}

TOLERANCE = Decimal("0.01")  # cent-level float noise guard, NOT a business threshold

_TWO_PLACES = Decimal("0.01")


def _to_money(value: float) -> Decimal:
    """Convert a validated numeric value to a Decimal quantized to 2 decimals.

    Converts via `str(value)` (not `Decimal(value)` directly) to avoid pulling
    in a float's binary imprecision before rounding.
    """
    return Decimal(str(value)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _validate_number(value: object, field_name: str) -> tuple[bool, str]:
    """Validate that `value` is a finite, non-negative number.

    Returns `(True, "")` when valid, or `(False, message)` naming the field
    and echoing the raw value when invalid. Never raises — covers both
    `amount` and `reported_tax` (DRY, per design.md).
    """
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False, f"{field_name} must be a finite number >= 0; got {value!r}."
    if not math.isfinite(numeric_value) or numeric_value < 0:
        return False, f"{field_name} must be a finite number >= 0; got {value!r}."
    return True, ""


def _calculate_discrepancy(
    amount: float, region: str, reported_tax: Optional[float] = None
) -> dict:
    """Pure core: expected-tax lookup and optional match/mismatch verdict.

    No I/O, no global mutable state. See design.md's Interfaces / Contracts
    for the exact shapes A-D returned here.
    """
    raw_region = region
    normalized_region = (region or "").strip().upper()
    rate = REGION_TAX_RATES.get(normalized_region)

    # Region is validated first (short-circuits before amount validation):
    # an unknown region has nothing to compute against.
    if rate is None:
        known_regions = ", ".join(sorted(REGION_TAX_RATES))
        return {
            "known_region": False,
            "region": raw_region,
            "message": f"Unknown region '{raw_region}'. Known regions: {known_regions}.",
        }

    amount_valid, amount_message = _validate_number(amount, "amount")
    if not amount_valid:
        return {
            "known_region": True,
            "valid_input": False,
            "region": normalized_region,
            "message": amount_message,
        }

    if reported_tax is not None:
        reported_valid, reported_message = _validate_number(reported_tax, "reported_tax")
        if not reported_valid:
            return {
                "known_region": True,
                "valid_input": False,
                "region": normalized_region,
                "message": reported_message,
            }

    amount_money = _to_money(amount)
    expected_tax_money = (amount_money * rate).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    result: dict = {
        "known_region": True,
        "valid_input": True,
        "region": normalized_region,
        "amount": float(amount_money),
        "tax_rate": float(rate),
        "expected_tax": float(expected_tax_money),
    }

    if reported_tax is None:
        return result

    # Tolerance/match is decided on the *raw* reported value (full precision,
    # before display rounding) so cent-level float noise is absorbed instead
    # of masked by quantization first.
    reported_raw = Decimal(str(reported_tax))
    delta_raw = reported_raw - expected_tax_money
    match = abs(delta_raw) < TOLERANCE

    reported_money = _to_money(reported_tax)
    delta_money = delta_raw.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    if expected_tax_money == 0:
        delta_pct: Optional[float] = None
    else:
        delta_pct_money = (delta_raw / expected_tax_money * 100).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )
        delta_pct = float(delta_pct_money)

    result["reported_tax"] = float(reported_money)
    result["delta"] = float(delta_money)
    result["delta_pct"] = delta_pct
    result["match"] = match
    return result


@tool
def calculate_tax_discrepancy(
    amount: float, region: str, reported_tax: Optional[float] = None
) -> dict:
    """Compute the tax expected for a region and, if a reported tax is given,
    how far it deviates.

    Args:
        amount: Net taxable base (the ERP order's net_amount), NOT the total.
        region: ERP region code, e.g. "EU-ES", "EU-DE", "LATAM-CO".
        reported_tax: The tax actually charged. Omit to get only the expected tax.
    """
    return _calculate_discrepancy(amount, region, reported_tax)
