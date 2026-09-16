# Proposal: F-B2 — Tax Discrepancy Logic (`calculate_tax_discrepancy`)

## Intent

F-B5's choice between `create_erp_adjustment` and `notify_human` rests on one number: how far an
invoice's tax deviates from the tax expected for its region. Leaving that arithmetic to the LLM is
the weakest link on a financial surface. F-B2 makes it a deterministic pure-Python tool, and closes
F-B1's recorded open question by owning the region codes and rates.

## Scope

### In Scope
- `app/tools/tax_discrepancy.py`: `calculate_tax_discrepancy` as a LangChain `@tool`, docstring/args
  schema sufficient for function calling.
- Static `REGION_TAX_RATES` pinned to F-B1's seeded data: `EU-ES` 21%, `EU-DE` 19%, `LATAM-CO` 19%.
- Expected tax + match/mismatch verdict with signed absolute and percentage delta, under a small
  absolute tolerance so float noise is not a mismatch.
- Tool-readable results for unknown region and invalid amount — never an exception.
- pytest over F-B1's seed cases: clean, under-tax, over-tax, wrong-region, unknown region.

### Out of Scope
- Editing `erp_data.py` / `erp_seed.py` (F-B1 merged, untouched); F-B3, F-B4, F-B5, F-B6.
- Configurable/DB-backed rate engine, effective dates, per-product rates — a static dict is the
  correct scope for this mock.
- Currency conversion, DB, network, or any I/O.

## Capabilities

### New Capabilities
- `tax-discrepancy`: expected-tax lookup and invoice-vs-expected deviation verdict, as an agent tool.

### Modified Capabilities
- None. `erp-data-access` requirements are unchanged; the rate alignment resolves an open question
  recorded in F-B1's design, not spec behavior.

## Approach

One module, no layers: rate table, one pure function, one `@tool` adapter. `Decimal` half-up at 2
decimals internally to keep seeded cents exact — mirroring F-B1's `Numeric(12,2)`-in / `float`-out
boundary — returning a flat JSON-serializable dict. Unknown region returns `{"known_region": False,
...}`, mirroring F-B1's readable not-found so the agent reasons about the miss instead of aborting
its ReAct step.

**Needs confirmation:** `(amount, region)` cannot express a discrepancy — nothing to compare
against. Recommended: keep it, add optional `reported_tax: float | None = None`. Supplied → verdict;
omitted → expected tax only. Preserves the planned call shape, moves comparison out of the LLM.

## Affected Areas

| Area | Impact | Description |
|------|--------|------------|
| `app/tools/tax_discrepancy.py` | New | Rate table + pure function + `@tool` adapter |
| `tests/test_tax_discrepancy.py` | New | Unit tests over F-B1 seed cases |
| `app/tools/erp_seed.py` | Unchanged | Its documented rates become authoritative here |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Rates drift from seeded amounts, corrupting every verdict | Med | Pin to seed; assert ORD-1001/1002/1003 are clean |
| `amount` read as gross total, not net base | Med | Document as taxable base in docstring; spec explicitly |
| Float equality flags a correct invoice | Med | `Decimal` + tolerance, tested at the boundary |
| Optional param diverges from planning doc signature | Low | Flagged above for confirmation before spec |

## Rollback Plan

Additive, isolated, zero external state: pure function, no I/O, no writes, no ERP adjustment, no
PII. Nothing imports it yet (F-B5 does not exist). Rollback = delete `app/tools/tax_discrepancy.py`
and `tests/test_tax_discrepancy.py`, or drop `feature/f-b2-tax-discrepancy`. F-B1 and the seeded
database are untouched either way.

## Dependencies

- None new — `langchain-core` and `pytest` already in `requirements.txt` from F-B1.
- No feature dependencies; F-B2 runs parallel to F-B1/B3/B4.

## Success Criteria

- [ ] F-B1 clean-match orders evaluate as matches; `ORD-1004`/`ORD-1005` report exact signed deltas
      (−60.00 / +60.00).
- [ ] Unknown region and invalid amount return structured results, no exception raised.
- [ ] No I/O, DB, or global mutable state — pure and importable standalone.
- [ ] Binds to `create_agent` with no glue; `pytest -v` green with tests that fail if the rate table
      or delta math breaks.
