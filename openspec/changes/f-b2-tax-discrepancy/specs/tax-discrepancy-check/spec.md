# Tax Discrepancy Check Specification

## Purpose

Deterministic, pure-Python expected-tax lookup and invoice-vs-expected
deviation verdict for a seeded region rate table, exposed as a LangChain tool
so F-B5's adjustment/escalation choice never depends on LLM arithmetic.

## Requirements

### Requirement: Tool Interface

The system MUST expose a LangChain tool `calculate_tax_discrepancy(amount:
float, region: str, reported_tax: float | None = None)` decorated with
`@tool`, with a docstring/args schema sufficient for LLM function calling.
The docstring MUST state explicitly that `amount` is the net taxable base
(the seeded `net_amount`), not the gross `total_amount`. All arithmetic MUST
execute in Python and MUST NOT be delegated to the LLM.

#### Scenario: Tool is bindable by the agent

- GIVEN `app/tools/tax_discrepancy.py` is imported
- WHEN `calculate_tax_discrepancy` is passed to `create_agent`'s tool list
- THEN the agent binds it with no extra glue code

#### Scenario: amount is documented as the net base, not gross total

- GIVEN the tool's docstring/args schema
- WHEN a caller inspects the `amount` parameter description
- THEN it identifies `amount` as the net taxable base, distinct from any
  gross/total amount

### Requirement: Region Rate Table

The system MUST maintain a static `REGION_TAX_RATES` mapping pinned to F-B1's
seeded values: `EU-ES` 21%, `EU-DE` 19%, `LATAM-CO` 19%.

#### Scenario: Expected tax matches seeded clean-match orders

- GIVEN seeded orders `ORD-1001` (EU-ES, net 1000.00), `ORD-1002` (EU-DE, net
  2000.00), `ORD-1003` (LATAM-CO, net 500.00)
- WHEN `calculate_tax_discrepancy` computes expected tax for each region/net
  pair with no `reported_tax`
- THEN the expected tax equals the seeded `tax_amount` for each order
  (210.00, 380.00, 95.00 respectively)

### Requirement: Expected-Tax-Only Mode

When `reported_tax` is omitted (`None`), the system MUST return only the
computed expected tax for the given `amount`/`region`, with no match/mismatch
verdict or delta fields.

#### Scenario: Expected tax without a reported value

- GIVEN `amount=1000.00`, `region="EU-ES"`, `reported_tax` omitted
- WHEN `calculate_tax_discrepancy(1000.00, "EU-ES")` is called
- THEN the result contains the expected tax (210.00) for that region
- AND the result contains no match/mismatch verdict and no delta

### Requirement: Full Verdict Mode

When `reported_tax` is supplied, the system MUST return a verdict comparing
`reported_tax` to the expected tax, including a signed absolute delta
(`reported_tax - expected_tax`) and a percentage delta.

#### Scenario: Clean match verdict

- GIVEN `amount=1000.00`, `region="EU-ES"`, `reported_tax=210.00`
- WHEN `calculate_tax_discrepancy(1000.00, "EU-ES", 210.00)` is called
- THEN the result reports a match verdict with a zero (or tolerance-bound)
  delta

#### Scenario: Under-tax mismatch with correct delta sign

- GIVEN seeded `ORD-1004`: `amount=1000.00`, `region="EU-ES"`,
  `reported_tax=150.00` (expected 210.00)
- WHEN `calculate_tax_discrepancy(1000.00, "EU-ES", 150.00)` is called
- THEN the result reports a mismatch verdict with signed delta `-60.00`

#### Scenario: Over-tax mismatch with correct delta sign

- GIVEN seeded `ORD-1005`: `amount=1000.00`, `region="EU-DE"`,
  `reported_tax=250.00` (expected 190.00)
- WHEN `calculate_tax_discrepancy(1000.00, "EU-DE", 250.00)` is called
- THEN the result reports a mismatch verdict with signed delta `+60.00`

### Requirement: Float-Tolerance Boundary

The system MUST apply a small absolute cent-level tolerance to the delta so
float noise never produces a false mismatch. This tolerance MUST NOT
substitute for any business "close enough" threshold. Root-cause inference
(e.g. matching a different region's rate) is out of scope.

#### Scenario: Reported tax within cent-level tolerance of expected

- GIVEN `amount=1000.00`, `region="EU-ES"` (expected tax 210.00),
  `reported_tax=210.004999...` (a float-noise value within the tolerance)
- WHEN `calculate_tax_discrepancy` compares `reported_tax` to expected tax
- THEN the result reports a match verdict, not a mismatch

#### Scenario: Reported tax just outside tolerance is a mismatch

- GIVEN `amount=1000.00`, `region="EU-ES"` (expected tax 210.00),
  `reported_tax=210.02` (one cent beyond the tolerance)
- WHEN `calculate_tax_discrepancy` compares `reported_tax` to expected tax
- THEN the result reports a mismatch verdict with the corresponding delta

### Requirement: Unknown Region Handling

The system MUST return `{"known_region": False, ...}` and MUST NOT raise an
unhandled exception when `region` is not in `REGION_TAX_RATES`, in either
expected-tax-only or full verdict mode.

#### Scenario: Unknown region in expected-tax-only mode

- GIVEN `region="APAC-JP"` is not in `REGION_TAX_RATES`
- WHEN `calculate_tax_discrepancy(1000.00, "APAC-JP")` is called
- THEN the tool returns `{"known_region": False, ...}` with no exception
  raised, and no expected-tax value is computed

#### Scenario: Unknown region in full verdict mode

- GIVEN `region="APAC-JP"` is not in `REGION_TAX_RATES`
- WHEN `calculate_tax_discrepancy(1000.00, "APAC-JP", 190.00)` is called
- THEN the tool returns `{"known_region": False, ...}` with no exception
  raised, and no match/mismatch verdict is computed
