"""Mocked agent action tools: simulated ERP adjustment and human escalation.

Both tools are deterministic mocks (see design.md): no `uuid`/timestamp, no
real side effect, never raise. `create_erp_adjustment` MUST NOT write to
`erp_orders` — it returns a simulated receipt only; `applied` is a literal
`False` so the mock is legible to the model, the reviewer and the test
alike. `notify_human` simulates a notification with no real transport;
`notified` is likewise a literal `False`.

`adjustment_amount` is deliberately NOT `delta` (F-B2's *observed*
percentage deviation, `delta_pct`) — this is the *correction to apply*,
computed by the model as `expected_tax - reported_tax` per the
`SYSTEM_PROMPT`. Distinct names prevent the model conflating the two (see
design.md Open Questions).
"""

from __future__ import annotations

import math
from typing import Optional

from langchain_core.tools import tool


def _clean_order_id(order_id: object) -> str:
    """Coerce and strip `order_id`. Never raises; non-str input becomes "" ."""
    if not isinstance(order_id, str):
        return ""
    return order_id.strip()


def _clean_reason(reason: object) -> str:
    """Coerce `reason` to a plain string. Never raises regardless of content —
    hostile/prompt-injection-style free text is passed through as inert data,
    never interpreted (mirrors F-B1/F-B2's never-raise convention)."""
    if isinstance(reason, str):
        return reason
    return "" if reason is None else str(reason)


def _validate_amount(value: object) -> tuple[bool, Optional[float]]:
    """Validate that `value` coerces to a finite float. Returns `(True, amount)`
    when valid, `(False, None)` otherwise. Never raises."""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False, None
    if not math.isfinite(numeric_value):
        return False, None
    return True, numeric_value


@tool
def create_erp_adjustment(order_id: str, adjustment_amount: float, reason: str) -> dict:
    """Simulate applying a tax adjustment to an ERP order.

    MOCKED: never writes to `erp_orders`; returns a simulated receipt only.
    Call this exactly once, only when the decision policy allows an
    auto-adjust (see the system prompt) — never both this and
    `notify_human` for the same order.

    Args:
        order_id: The ERP order identifier, e.g. "ORD-1004".
        adjustment_amount: expected_tax - reported_tax, the correction to apply.
        reason: One sentence citing delta_pct and the regulation relied on.
    """
    cleaned_order_id = _clean_order_id(order_id)
    amount_valid, amount = _validate_amount(adjustment_amount)

    if not cleaned_order_id or not amount_valid:
        return {
            "status": "rejected",
            "action": "erp_adjustment",
            "order_id": order_id,
            "applied": False,
            "message": "Invalid order_id or adjustment_amount; no adjustment simulated.",
        }

    cleaned_reason = _clean_reason(reason)
    return {
        "status": "simulated",
        "action": "erp_adjustment",
        "adjustment_id": f"ADJ-{cleaned_order_id}",
        "order_id": cleaned_order_id,
        "adjustment_amount": amount,
        "reason": cleaned_reason,
        "applied": False,
        "message": (
            f"Simulated adjustment of {amount} for order {cleaned_order_id}; "
            "no ERP write performed."
        ),
    }


@tool
def notify_human(order_id: str, reason: str) -> dict:
    """Simulate escalating an order to a human reviewer.

    MOCKED: no real notification transport. Call this exactly once, whenever
    the decision policy requires escalation (see the system prompt) —
    never both this and `create_erp_adjustment` for the same order.

    Args:
        order_id: The ERP order identifier, e.g. "ORD-1005".
        reason: One sentence explaining why this order needs human review.
    """
    cleaned_order_id = _clean_order_id(order_id)

    if not cleaned_order_id:
        return {
            "status": "rejected",
            "action": "human_escalation",
            "order_id": order_id,
            "notified": False,
            "message": "Invalid order_id; no escalation simulated.",
        }

    cleaned_reason = _clean_reason(reason)
    return {
        "status": "simulated",
        "action": "human_escalation",
        "ticket_id": f"ESC-{cleaned_order_id}",
        "order_id": cleaned_order_id,
        "reason": cleaned_reason,
        "notified": False,
        "message": (
            f"Simulated escalation ticket for order {cleaned_order_id}; "
            "no notification sent."
        ),
    }
