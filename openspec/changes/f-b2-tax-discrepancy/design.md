# Design: F-B2 — Tax Discrepancy Logic (`calculate_tax_discrepancy`)

## Technical Approach

One file: `app/tools/tax_discrepancy.py` = a `REGION_TAX_RATES` constant, a private pure core, and a
`@tool` delegate. Per `architecture-patterns` Decision Gates the signals are zero entities, zero
integrations, no invariants, no read/write divergence → **no pattern; a plain function is the honest
choice**. F-B1's engine/session/seed trio has no analogue: nothing to persist, inject, or swap.
Mirroring its shape would add structure with no second reason to change (`solid-principles`
YAGNI/KISS, `ponytail`). The one split kept is SRP: arithmetic changes hit the core, LLM-contract
changes hit the `@tool` docstring/schema.

Money is `Decimal` end-to-end — rates as `Decimal`, products quantized to 2 decimals
`ROUND_HALF_UP` — with `float()` only when building the returned dict. Same `Numeric(12,2)`-in /
JSON-safe-`float`-out boundary F-B1 established.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Rate source | `REGION_TAX_RATES: dict[str, Decimal]`: `EU-ES` `0.21`, `EU-DE` `0.19`, `LATAM-CO` `0.19` | DB table, YAML/env config, rate "engine" | Confirmed against `app/tools/erp_seed.py` (docstring + `SEED_ORDERS`: 1000→210, 2000→380, 500→95). Three fixed rates, no effective dates → a dict, not configuration |
| Module structure | private `_calculate_discrepancy(...)` core + `@tool` thin delegate | Decorate the core directly, test via `.func` | Two reasons to change (math vs function-calling contract); core stays unit-testable without a `StructuredTool` round-trip — F-B1's `_fetch_order` / `get_erp_data` layering |
| Two modes | one tool, optional `reported_tax: float \| None = None` | Two tools; required param | Decision 1: omitted → expected tax only; supplied → verdict. Keeps the planned call shape |
| `amount` semantics | net taxable base = F-B1 `net_amount` | Gross total (back-solve the base) | Decision 2; back-solving silently changes the answer when the caller is wrong. Docstring states it so `total_amount` is not passed by accident |
| Delta sign | `delta = reported_tax − expected_tax` | `abs(delta)`; `expected − reported` | Success criteria: ORD-1004 → `−60.00` (under), ORD-1005 → `+60.00` (over). The sign is the signal F-B5 needs |
| Match test | `abs(delta) < Decimal("0.01")` | `==`; percentage/business threshold | Decision 5: cent-level float-noise guard only. A business threshold is F-B5's policy call |
| Unknown region | `{"known_region": False, "region": <raw>, "message": ...}` | `raise ValueError`; default rate | Decision 4. An exception aborts the ReAct step; a default rate invents a financial verdict |
| Invalid input | `{"known_region": True, "valid_input": False, ...}`, never raises | Raise; coerce garbage to `0` | Same readable-failure principle. One validator covers both numbers (DRY); the message names the field |
| Region input | `.strip().upper()`, echo raw on a miss | Exact-match only | One line of robustness against `"eu-es"`; echoing raw keeps the miss debuggable (as F-B1 does for `order_id`) |
| Reverse region inference | Out of scope | Infer which region's rate the tax matches | Decision 6. ORD-1006/1007 still get a correct signed delta; naming the *other* region is F-B5's reasoning, not arithmetic |

## Data Flow

    user query ──> create_agent (ReAct)
                      │ 1. get_erp_data("ORD-1004")      ──> SQLite (F-B1)
                      │    {net_amount, tax_amount, region, status}
                      │ 2. calculate_tax_discrepancy(
                      │        amount=net_amount, region=region,
                      │        reported_tax=tax_amount)
                      ▼
            @tool adapter ──> _calculate_discrepancy()  [pure, no I/O]
                                  │ region → REGION_TAX_RATES  (miss → known_region: False)
                                  │ amount/reported_tax → Decimal (invalid → valid_input: False)
                                  │ expected = quantize(amount * rate)
                                  │ delta = reported − expected ; match = |delta| < 0.01
                                  ▼
                              flat dict (floats) ──> LLM context ──> F-B5 adjust | notify

No DB, network, file, or global mutable state — deterministic and importable standalone (proposal
success criterion 3).

## File Changes

| File | Action | Description |
|---|---|---|
| `app/tools/tax_discrepancy.py` | Create | `REGION_TAX_RATES`, `_to_money`, `_calculate_discrepancy`, `@tool calculate_tax_discrepancy` |
| `tests/test_tax_discrepancy.py` | Create | Seed-pinned rates, both modes, deltas, tolerance, failure shapes |
| `app/tools/erp_seed.py`, `app/tools/erp_data.py` | Unchanged | F-B1 is merged; its rates become authoritative here (proposal out-of-scope) |
| `tests/conftest.py`, `requirements.txt` | Unchanged | No fixture and no dependency needed — pure function, `langchain-core`/`pytest` already present |

## Interfaces / Contracts

```python
REGION_TAX_RATES: dict[str, Decimal] = {
    "EU-ES": Decimal("0.21"),
    "EU-DE": Decimal("0.19"),
    "LATAM-CO": Decimal("0.19"),
}
TOLERANCE = Decimal("0.01")   # cent-level float noise, NOT a business threshold

@tool
def calculate_tax_discrepancy(
    amount: float, region: str, reported_tax: float | None = None
) -> dict:
    """Compute the tax expected for a region and, if a reported tax is given,
    how far it deviates.

    Args:
        amount: Net taxable base (the ERP order's net_amount), NOT the total.
        region: ERP region code, e.g. "EU-ES", "EU-DE", "LATAM-CO".
        reported_tax: The tax actually charged. Omit to get only the expected tax.
    """
```

Return shapes (flat, JSON-serializable, scalars only):

```python
# A. expected-only (reported_tax omitted)
{"known_region": True, "valid_input": True, "region": "EU-ES",
 "amount": 1000.0, "tax_rate": 0.21, "expected_tax": 210.0}

# B. full verdict (reported_tax supplied) = A + these four keys
{..., "reported_tax": 150.0, "delta": -60.0, "delta_pct": -28.57, "match": False}

# C. unknown region (short-circuits before amount validation)
{"known_region": False, "region": "EU-XX",
 "message": "Unknown region 'EU-XX'. Known regions: EU-DE, EU-ES, LATAM-CO."}

# D. invalid input (non-finite, non-numeric, or negative amount/reported_tax)
{"known_region": True, "valid_input": False, "region": "EU-ES",
 "message": "amount must be a finite number >= 0; got -5.0."}
```

Caller contract: proceed only when `result.get("known_region")` and `result.get("valid_input")` are
both truthy. `delta_pct` is `delta / expected_tax * 100` quantized to 2 decimals, and is `None` when
`expected_tax == 0` (amount `0`) — division by zero is a value, not an exception.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit — anti-drift | Rate table still matches F-B1's seed | Import `SEED_ORDERS`, parametrize ORD-1001/1002/1003, assert `match is True` and `delta == 0.0`. Fails if either side drifts |
| Unit — deltas | ORD-1004 → `-60.00`, ORD-1005 → `+60.00`, `match is False` | Exact equality on 2-decimal results |
| Unit — wrong region | ORD-1006 (168 @ EU-DE), ORD-1007 (126 @ LATAM-CO) | Correct signed delta; assert no inferred-region key exists |
| Unit — mode A | `reported_tax` omitted | Exact key set (no `delta`/`match`/`reported_tax`) |
| Unit — tolerance | `expected ± 0.009` matches, `± 0.01` does not | Boundary on both sides |
| Unit — failures | Unknown/empty/lowercase region; `amount` negative, `"abc"`, `NaN`, `inf`; bad `reported_tax` | Assert shapes C/D — no exception may escape |
| Unit — shape | All four shapes | `json.dumps(result)` must not raise; scalars only |
| Integration | Tool is bindable | `.name` / `.args_schema` exist; `.invoke({...})` equals the core's dict |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary; the module does arithmetic and reads a constant dict. It does feed a
sensitive surface (F-B5's ERP adjustment, per `CLAUDE.md`), which is precisely why the math is
deterministic Python with seed-pinned tests instead of LLM reasoning. No PII or salary data.

## Migration / Rollout

No migration required. Additive new module with no importers until F-B5 exists; no schema, no data,
no feature flag. Rollback = delete the two new files, per the proposal.

## Open Questions

- [ ] None blocking. This design closes F-B1's recorded open question: `EU-ES` 21%, `EU-DE` 19%,
      `LATAM-CO` 19% are now owned by `REGION_TAX_RATES` and locked by the anti-drift test.
