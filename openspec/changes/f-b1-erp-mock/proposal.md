# Proposal: F-B1 — Mock ERP Data Layer (`get_erp_data`)

## Intent

The reconciliation agent (F-B5) cannot compare a logistics invoice against the ERP without a
way to fetch an order's ERP record. The technical test allows a mocked data source, but its
rubric explicitly grades **parametrized SQL** — even simulated. F-B1 delivers the first Track B
slice: a LangChain tool `get_erp_data(order_id)` over SQLite/SQLAlchemy with seeded, realistic
records, so later features have a stable ERP read contract instead of ad-hoc fixtures.

## Scope

### In Scope
- `app/tools/erp_data.py`: `get_erp_data(order_id: str)` exposed as a LangChain tool (`@tool`),
  with docstring/args schema good enough for LLM function calling.
- SQLAlchemy engine/session + SQLite file (or configurable path) as the mock "SQL Server".
- Parametrized queries only (bound parameters / ORM); zero string-interpolated SQL.
- Seed script + schema for a small realistic dataset: `order_id`, amounts (net, tax, total),
  `region`, `status`, invoice/ERP fields relevant to tax-discrepancy cases.
- Deterministic not-found / empty result behavior returned as tool-readable data, not a crash.
- At least one pytest test per project rule (hit, miss, and injection-style `order_id`).

### Out of Scope
- `calculate_tax_discrepancy` (F-B2), RAG (F-B3), security middleware (F-B4), agent (F-B5), API (F-B6).
- Any real SQL Server / network ERP connection, writes, or `create_erp_adjustment`.
- PII or salary fields — the guardrail (F-B4) does not exist yet; keep this dataset free of them.

## Capabilities

### New Capabilities
- `erp-data-access`: read-only lookup of ERP order records by `order_id`, exposed as an agent tool.

### Modified Capabilities
- None (first Track B feature; `openspec/specs/` is empty).

## Approach

Thin hexagonal slice: a small SQLAlchemy layer (engine + table/model + one query function) wrapped
by a LangChain `@tool` adapter. The tool returns a plain dict/`None`-shaped result so the LLM sees
structured data. Seeding runs from an idempotent script/fixture so tests and demos share one dataset.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/tools/erp_data.py` | New | Tool + query logic |
| `app/` package init, seed script, SQLite artifact | New | Bootstrap for first code feature |
| `tests/` (+ `conftest.py`) | New | First pytest runner setup for the repo |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Tool return shape churns when F-B5/F-B2 integrate | Med | Keep shape flat and documented in the spec |
| Mock schema misses fields F-B2 needs for discrepancy | Med | Seed region + net/tax/total explicitly |
| Accidental string-built SQL | Low | Bound params only; test with a quote-bearing `order_id` |

## Rollback Plan

Additive, isolated, low risk: no existing code, no real ERP data, no writes. Rollback = delete
`app/tools/erp_data.py`, the seed script, the SQLite file, and the tests (or drop the
`feature/f-b1-erp-mock` branch). Nothing else in the repo depends on it yet.

## Dependencies

- `sqlalchemy`, `langchain` (+`pytest`) added to `requirements.txt`. No feature dependencies.

## Success Criteria

- [ ] `get_erp_data("<seeded id>")` returns the seeded ERP record; unknown id returns a clean not-found result.
- [ ] No SQL string interpolation anywhere in the module; a quote/`--` bearing `order_id` is harmless.
- [ ] Tool is importable and bindable by `create_agent` without extra glue.
- [ ] `pytest -v` green with at least one test that fails if the query logic breaks.
