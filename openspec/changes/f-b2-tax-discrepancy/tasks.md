# Tasks: F-B2 — Tax Discrepancy Logic

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 350 (core ~150 + tests ~200) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | N/A |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: N/A
400-line budget risk: Low

## Phase 1: Foundation (Infrastructure)

- [x] 1.1 Create `app/tools/tax_discrepancy.py` with module docstring and imports (`Decimal`, `LangChain @tool`)
- [x] 1.2 Define `REGION_TAX_RATES: dict[str, Decimal]` constant with `EU-ES` (0.21), `EU-DE` (0.19), `LATAM-CO` (0.19)
- [x] 1.3 Define `TOLERANCE = Decimal("0.01")` constant for cent-level float-noise guard

## Phase 2: Core Implementation

- [x] 2.1 Implement `_to_money(value: float) -> Decimal` helper: convert float to Decimal, quantize to 2 decimals (ROUND_HALF_UP)
- [x] 2.2 Implement `_calculate_discrepancy()` core pure function with full signature and logic:
  - Validate region (strip, upper-case) against `REGION_TAX_RATES`; return `known_region: False` shape if miss
  - Validate `amount` and `reported_tax` (finite, numeric, >= 0); return `valid_input: False` shape if invalid
  - Calculate `expected_tax = quantize(amount * rate)`, `delta = reported_tax - expected_tax` (if supplied)
  - Calculate `delta_pct = delta / expected_tax * 100` (or None if expected_tax == 0)
  - Return flat dict (all floats) with exact key sets per design doc shapes A–D
- [x] 2.3 Implement `@tool calculate_tax_discrepancy()` decorator and delegate: wrap core, accept `amount`, `region`, `reported_tax: float | None = None`
- [x] 2.4 Verify module is importable and tool has `.name`, `.args_schema` (LangChain contract)

## Phase 3: Testing — Anti-Drift and Scenarios

- [x] 3.1 Create `tests/test_tax_discrepancy.py` with imports (`SEED_ORDERS` from `erp_seed.py`, `pytest`, `calculate_tax_discrepancy`)
- [x] 3.2 Write anti-drift test: parametrize over ORD-1001, ORD-1002, ORD-1003 from `SEED_ORDERS`; verify `match is True` and `delta == 0.0` for each
- [x] 3.3 Write delta tests: call with ORD-1004 (1000 net, EU-ES, 150 tax) → assert `delta == -60.0`, `match is False`; ORD-1005 (1000 net, EU-DE, 250 tax) → assert `delta == +60.0`, `match is False` (looked up live from `SEED_ORDERS` rather than the task's stated 2000/440 pair, which does not match the actual seeded record or design.md's own scenario — see Deviations)
- [x] 3.4 Write wrong-region tests: ORD-1006 (800 net, EU-DE, 168 tax) and ORD-1007 (600 net, LATAM-CO, 126 tax); verify correct signed deltas, no inferred-region key
- [x] 3.5 Write mode-A test (reported_tax omitted): call with (1000, "EU-ES"); assert keys = {known_region, valid_input, region, amount, tax_rate, expected_tax} only (no delta, match, reported_tax)

## Phase 4: Testing — Boundaries, Failures, and Integration

- [x] 4.1 Write tolerance boundary tests: (1000, "EU-ES", 210.009) → `match is True`; (1000, "EU-ES", 210.010) → `match is False`; (1000, "EU-ES", 209.991) → `match is True`; (1000, "EU-ES", 209.990) → `match is False`
- [x] 4.2 Write failure-shape tests (no exception may escape):
  - Unknown region ("APAC-JP", 1000) → assert `known_region is False`, message names the region, lists known regions
  - Invalid amounts (-5, "abc", NaN, inf) and invalid `reported_tax` with region EU-ES → assert `valid_input is False`, message names the field (0 is valid per spec's ">= 0" and design's `delta_pct: None` case, so it is asserted as *valid*, not invalid — see Deviations)
  - Empty region ("") → unknown-region shape; lowercase region ("eu-es") → normalized and matched as `known_region: True`, `region: "EU-ES"`, per design.md's explicit `.strip().upper()` robustness rule — see Deviations
- [x] 4.3 Write shape/serialization test: all four result shapes (A, B, C, D per design) pass `json.dumps()`; all values are scalars, no nested objects
- [x] 4.4 Write tool bindability test: verify tool `.name == "calculate_tax_discrepancy"`, `.args_schema` is callable, `.invoke({...})` matches core result dict
- [x] 4.5 Run full test suite: `pytest -v` green; no test may be skipped

## Summary

- **Total tasks**: 14
- **Implementation order**: Phases 1–2 first (infrastructure + core), then Phases 3–4 in parallel (testing)
- **Dependency chain**: Phase 1 must complete before Phase 2; Phases 3–4 depend on Phase 2 only
- **Key success gates**:
  - Module imports cleanly with no external I/O
  - All failure shapes return dicts, never raise
  - Anti-drift test locks rates to F-B1 seed
  - Tool binds to LangChain `create_agent` without glue code
