"""Idempotent seed data for the mock ERP database.

Ships a small, realistic dataset covering the cases F-B2 (tax discrepancy)
and F-B5 (reconciliation agent) need to exercise: clean matches, tax
mismatches, a wrong-region record, and cancelled/pending orders.

Region tax rates used to derive the seeded amounts below (placeholder rates
for this mock; MUST be re-confirmed against F-B2's
`calculate_tax_discrepancy(amount, region)` at integration time per design.md):
    - EU-ES:    21% (Spanish VAT)
    - EU-DE:    19% (German VAT)
    - LATAM-CO: 19% (Colombian IVA, mock rate)

`ORD-9999` is deliberately NOT seeded — it is the documented id used by the
miss/not-found test case.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# fmt: off
SEED_ORDERS = [
    # --- Clean matches: tax_amount == net_amount * region rate ---
    {  # EU-ES @ 21%
        "order_id": "ORD-1001", "net_amount": Decimal("1000.00"),
        "tax_amount": Decimal("210.00"), "total_amount": Decimal("1210.00"),
        "region": "EU-ES", "status": "confirmed",
    },
    {  # EU-DE @ 19%
        "order_id": "ORD-1002", "net_amount": Decimal("2000.00"),
        "tax_amount": Decimal("380.00"), "total_amount": Decimal("2380.00"),
        "region": "EU-DE", "status": "confirmed",
    },
    {  # LATAM-CO @ 19%
        "order_id": "ORD-1003", "net_amount": Decimal("500.00"),
        "tax_amount": Decimal("95.00"), "total_amount": Decimal("595.00"),
        "region": "LATAM-CO", "status": "confirmed",
    },
    # --- Tax mismatch: tax_amount does not match the region's rate ---
    {  # EU-ES: correct tax would be 210.00 (21% of 1000.00); seeded under
        "order_id": "ORD-1004", "net_amount": Decimal("1000.00"),
        "tax_amount": Decimal("150.00"), "total_amount": Decimal("1150.00"),
        "region": "EU-ES", "status": "confirmed",
    },
    {  # EU-DE: correct tax would be 190.00 (19% of 1000.00); seeded over
        "order_id": "ORD-1005", "net_amount": Decimal("1000.00"),
        "tax_amount": Decimal("250.00"), "total_amount": Decimal("1250.00"),
        "region": "EU-DE", "status": "confirmed",
    },
    # --- Wrong region: tax_amount matches a *different* region's rate ---
    {  # tax is 21% of net (EU-ES rate) but region says EU-DE
        "order_id": "ORD-1006", "net_amount": Decimal("800.00"),
        "tax_amount": Decimal("168.00"), "total_amount": Decimal("968.00"),
        "region": "EU-DE", "status": "confirmed",
    },
    {  # tax is 21% of net (EU-ES rate) but region says LATAM-CO (19% band)
        "order_id": "ORD-1007", "net_amount": Decimal("600.00"),
        "tax_amount": Decimal("126.00"), "total_amount": Decimal("726.00"),
        "region": "LATAM-CO", "status": "confirmed",
    },
    # --- Non-confirmed statuses: must not be naively adjusted ---
    {  # cancelled, clean EU-ES @ 21%
        "order_id": "ORD-1008", "net_amount": Decimal("300.00"),
        "tax_amount": Decimal("63.00"), "total_amount": Decimal("363.00"),
        "region": "EU-ES", "status": "cancelled",
    },
    {  # pending, clean EU-DE @ 19%
        "order_id": "ORD-1009", "net_amount": Decimal("400.00"),
        "tax_amount": Decimal("76.00"), "total_amount": Decimal("476.00"),
        "region": "EU-DE", "status": "pending",
    },
]
# fmt: on

# ORD-9999 is intentionally absent from SEED_ORDERS — it is the documented,
# stable "missing order" id used by the not-found test.


def seed_database(engine: Engine) -> None:
    """Populate `erp_orders` from SEED_ORDERS, idempotently.

    Uses `Session.merge()` (upsert-by-primary-key) so re-running this
    function against an already-seeded database is a no-op: no duplicate
    rows are created and existing rows are refreshed to match SEED_ORDERS.
    """
    # Imported lazily to avoid a hard import-time dependency cycle with
    # erp_data (which imports seed_database from here on first engine init).
    from app.tools.erp_data import ErpOrder

    with Session(engine) as session:
        for record in SEED_ORDERS:
            session.merge(ErpOrder(**record))
        session.commit()


if __name__ == "__main__":
    from app.tools.erp_data import _get_engine

    seed_database(_get_engine())
    print(f"Seeded {len(SEED_ORDERS)} ERP order(s).")
