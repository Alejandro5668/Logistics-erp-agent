# ERP Data Access Specification

## Purpose

Read-only, LangChain-callable lookup of mocked ERP order records by
`order_id`, backed by SQLAlchemy over SQLite. Gives downstream agent features
(reconciliation, tax-discrepancy) a stable, injection-safe data contract
without a real ERP connection.

## Requirements

### Requirement: Tool Interface

The system MUST expose a LangChain tool `get_erp_data(order_id: str)`
decorated with `@tool`, with a docstring/args schema sufficient for LLM
function calling.

#### Scenario: Tool is bindable by the agent

- GIVEN `app/tools/erp_data.py` is imported
- WHEN `get_erp_data` is passed to `create_agent`'s tool list
- THEN the agent binds it with no extra glue code

### Requirement: Parametrized Query Execution

The system MUST execute all ERP lookups using bound parameters (ORM or
`text()` with bind params). The system MUST NOT build SQL via string
interpolation or concatenation with `order_id`.

#### Scenario: Clean matching lookup

- GIVEN a seeded order `ORD-1001` with matching net/tax/total, correct
  region, and status `completed`
- WHEN `get_erp_data("ORD-1001")` is called
- THEN the tool returns the full seeded record as a flat dict

#### Scenario: Quote/comment-bearing order_id is a literal, not code

- GIVEN a seeded dataset with at least one valid order
- WHEN `get_erp_data("ORD-1001' OR '1'='1")` or `get_erp_data("ORD-1001'; --")` is called
- THEN no SQL syntax error or driver exception is raised
- AND the deterministic not-found result is returned (the string is bound as
  one literal value that matches no row)
- AND no unintended rows (e.g. all orders) are ever returned

### Requirement: Deterministic Not-Found Behavior

The system MUST return a deterministic, tool-readable not-found result when
`order_id` matches no row, or is empty/malformed. The system MUST NOT raise
an unhandled exception.

#### Scenario: Unknown order_id

- GIVEN no seeded order has `order_id="ORD-9999"`
- WHEN `get_erp_data("ORD-9999")` is called
- THEN the tool returns a not-found result (e.g. `{"found": False, "order_id": "ORD-9999"}`) with no exception raised

#### Scenario: Empty or whitespace order_id

- GIVEN `order_id` is empty or whitespace-only
- WHEN `get_erp_data(order_id)` is called
- THEN the same deterministic not-found result is returned with no exception raised

### Requirement: Seeded Dataset Coverage

The system MUST ship an idempotent seed script producing a dataset covering
at minimum: a clean match, a tax mismatch, a wrong-region record, a missing
order (documented id with no row), and a cancelled/pending-status order.

#### Scenario: Tax mismatch and wrong-region records are retrievable as-is

- GIVEN a seeded order whose ERP `tax` differs from its expected value, and a
  seeded order whose `region` differs from the region implied by other fields
- WHEN `get_erp_data` is called with either order's id
- THEN the tool returns the record with the mismatched field intact — no
  correction or normalization applied

#### Scenario: Cancelled or pending record is retrievable

- GIVEN a seeded order with `status` of `cancelled` or `pending`
- WHEN `get_erp_data` is called with that id
- THEN the tool returns the record including that exact status value

#### Scenario: Re-running the seed script is idempotent

- GIVEN the seed script already populated the SQLite database
- WHEN the seed script runs again
- THEN no duplicate rows exist per `order_id` and the dataset matches a
  single run

### Requirement: Flat Return Shape

The system MUST return a plain flat dict per matched record (no nested ORM
objects) so the shape is JSON-serializable and stable for LLM consumption and
later features.

#### Scenario: Return shape is a flat dict

- GIVEN a seeded order matches the lookup
- WHEN `get_erp_data` returns successfully
- THEN the result is a `dict` with only scalar values (str, int, float, bool, None)
- AND it includes at minimum: `order_id`, net amount, tax amount, total
  amount, `region`, and `status`
