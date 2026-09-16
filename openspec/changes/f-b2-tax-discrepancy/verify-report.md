# Verification Report — f-b2-tax-discrepancy

**Change**: f-b2-tax-discrepancy
**Mode**: Full artifacts (proposal + specs + design + tasks) — OpenSpec persistence
**Branch**: feature/f-b2-tax-discrepancy (confirmed via `git branch --show-current`)
**Date**: 2026-09-16

## Completeness

- Tasks: 14/14 checked in `tasks.md` (Phases 1-4), matches implementation state. No unchecked tasks.
- Files present: `app/tools/tax_discrepancy.py`, `tests/test_tax_discrepancy.py`, per design.md's File Changes table. `erp_seed.py` / `erp_data.py` unchanged, as documented.

## Test Evidence

Command: `python -m pytest -v` (full suite, rootdir `C:\Repositorios\Logistics-erp-agent`)

```
collected 53 items
tests/test_erp_data.py ........................ 18 passed
tests/test_tax_discrepancy.py .................. 35 passed
53 passed in 0.42s-0.61s
```

Exit code: 0. No skips, no xfails, no warnings. 18 pre-existing F-B1 tests + 35 new F-B2 tests = 53, matching the apply phase's reported count exactly.

## Spec Compliance Matrix

`spec.md` contains 6 Requirements / 11 Scenarios total.

| Requirement | Scenario | Test(s) | Result |
|---|---|---|---|
| Tool Interface | Tool is bindable by the agent | `TestTaxDiscrepancyToolBindability::test_tool_exposes_name_and_args_schema`, `test_tool_invoke_matches_core_result` | PASS |
| Tool Interface | amount documented as net base, not gross | (no runtime assertion on docstring text) | UNTESTED — see WARNING-1 |
| Region Rate Table | Expected tax matches seeded clean-match orders (ORD-1001/2/3) | `TestTaxDiscrepancyAntiDrift` (parametrized) | PASS |
| Expected-Tax-Only Mode | Expected tax without reported value | `TestTaxDiscrepancyModeA::test_expected_tax_only_when_reported_tax_omitted` | PASS |
| Full Verdict Mode | Clean match verdict (1000/EU-ES/210.00) | `TestTaxDiscrepancyAntiDrift[ORD-1001]` (identical values) | PASS |
| Full Verdict Mode | Under-tax mismatch, delta -60.00 (ORD-1004) | `TestTaxDiscrepancyDeltas::test_ord_1004_under_tax_has_negative_delta` | PASS |
| Full Verdict Mode | Over-tax mismatch, delta +60.00 (ORD-1005) | `TestTaxDiscrepancyDeltas::test_ord_1005_over_tax_has_positive_delta` | PASS |
| Float-Tolerance Boundary | Reported tax within tolerance (210.004999) | `test_reported_tax_within_float_noise_tolerance_matches` | PASS |
| Float-Tolerance Boundary | Reported tax just outside tolerance (210.02) | `test_reported_tax_one_cent_beyond_tolerance_is_mismatch` | PASS |
| Unknown Region Handling | Expected-tax-only mode, unknown region | `test_unknown_region_mode_a_returns_known_region_false_no_exception` | PASS |
| Unknown Region Handling | Full verdict mode, unknown region | `test_unknown_region_full_verdict_mode_returns_known_region_false` | PASS |

10/11 scenarios have a passing runtime-covering test. 1/11 (docstring-content scenario) is satisfied only by static source inspection — see WARNING-1.

## Design Coherence

| Design decision | Code location | Verified |
|---|---|---|
| Decimal end-to-end, ROUND_HALF_UP, float() only at dict boundary | `_to_money`, `_calculate_discrepancy` | Yes |
| Private core plus thin @tool delegate (SRP) | `_calculate_discrepancy` / `calculate_tax_discrepancy` | Yes |
| Region validated before amount (short-circuit) | lines 67-88 | Yes |
| Delta sign = reported_tax minus expected_tax | line 119 | Yes, matches ORD-1004 (-60) / ORD-1005 (+60) |
| Match = abs(delta) < Decimal(0.01) on raw (pre-quantized) delta | lines 118-120 | Yes, boundary tests confirm strict less-than |
| Unknown region echoes raw (unnormalized) input | line 77 (raw_region) | Yes |
| Region normalization strip/upper | line 68 | Yes, tested |
| delta_pct = None when expected_tax == 0 | lines 125-126 | Implemented; not runtime-tested — see WARNING-3 |

## Deviation Review (3 flagged by apply phase)

1. Lowercase region normalized to KNOWN. Confirmed genuinely design-driven, not a shortcut: design.md Architecture Decisions table, Region input row, explicitly specifies strip/upper normalization against a lowercase example, with rationale that echoing raw keeps the miss debuggable. Code (tax_discrepancy.py line 68) and test (test_lowercase_region_is_normalized_and_still_known, with an inline comment citing design.md) match. Justified.

2. amount = 0 treated as VALID. Justified, but the framing given in the task needs one correction: spec.md itself contains no Requirement or Scenario about input validation at all. I grepped the full spec.md for valid_input, Invalid, and ">= 0" and found zero matches. The amount >= 0 contract (and the delta_pct = None rule for expected_tax == 0) is established entirely in design.md, not spec.md: the Interfaces/Contracts section's shape D error text and the Caller Contract paragraph stating delta_pct is None when expected_tax == 0 (amount 0) because division by zero is a value, not an exception. The implementation (tax_discrepancy.py lines 44-56, 125-126) and test (test_amount_zero_is_valid_not_invalid) match design.md faithfully. Justified by design.md, not by spec.md as the brief stated. This is a pre-existing spec/design traceability gap (input validation was never promoted from design into a formal spec Requirement), not an implementer shortcut.

3. ORD-1005 test values corrected to net=1000.00, region=EU-DE, tax=250.00. Confirmed against app/tools/erp_seed.py (lines 49-53): exact match. Also confirmed against spec.md's own Over-tax mismatch scenario (lines 82-85): amount=1000.00, region=EU-DE, reported_tax=250.00 (expected 190.00), signed delta +60.00 — identical values. tasks.md's literal 2000/440 pair was simply wrong; the test correctly looks up ORD-1005 live from SEED_ORDERS rather than hardcoding either the stale or corrected numbers, so it cannot drift again. Justified — tasks.md error, not an implementation shortcut.

## Anti-Drift Test Correctness

tests/test_tax_discrepancy.py imports SEED_ORDERS from app.tools.erp_seed (line 21) and parametrizes TestTaxDiscrepancyAntiDrift over ORD-1001, ORD-1002, ORD-1003, looking up each record live via a local _seed_order() helper rather than hardcoding amounts. The delta and wrong-region test classes (ORD-1004 through ORD-1007) use the same live-lookup pattern, which is stronger anti-drift protection than tasks.md's literal ask (limited to 1001-1003). Confirmed correct.

## Issues

CRITICAL: None.

WARNING:
1. Spec Scenario "amount is documented as the net base, not gross total" (Requirement: Tool Interface) has no automated test asserting docstring/args-schema content. Verified only via direct source read (tax_discrepancy.py lines 147-150 contain the required text). Per the hard rule that a scenario is compliant only with a passing runtime-covering test, this remains formally unproven at runtime, though risk is low since it is inherently a static documentation check.
2. The invalid-input contract (valid_input: False shapes, amount >= 0, delta_pct = None for expected_tax == 0) is documented only in design.md, with no corresponding spec.md Requirement/Scenario. Not a code defect — flagging for spec hygiene so a future spec revision can promote this business rule into a formal acceptance criterion.
3. No runtime test exercises delta_pct == None when expected_tax == 0 and reported_tax is supplied (full verdict mode with amount=0). Code correctly implements this per design.md (verified by inspection), but it is untested at runtime.

SUGGESTION:
- Consider adding one test: calculate_tax_discrepancy.invoke with amount 0.0, region EU-ES, reported_tax 5.0, asserting delta_pct is None, closing WARNING-3.

## Final Verdict

PASS WITH WARNINGS

53/53 tests passing (exit code 0), 14/14 tasks complete, 10/11 spec scenarios runtime-proven, all 3 flagged deviations independently confirmed as genuinely design/spec-justified (not shortcuts), anti-drift test correctly wired to F-B1's SEED_ORDERS. Three low-risk WARNINGs recorded (one docstring-content scenario untested at runtime, one spec/design traceability gap, one missing edge-case test) — none block archive.
