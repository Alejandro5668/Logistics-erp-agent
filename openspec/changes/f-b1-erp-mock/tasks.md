# Tasks: F-B1 — Mock ERP Data Layer (`get_erp_data`)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 340–380 (core code ~200, tests ~150, config ~30) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR: `feature/f-b1-erp-mock` |
| Delivery strategy | single-pr |
| Chain strategy | size-exception (not needed) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| Single | Complete ERP data-access layer + tests | PR 1 (feature/f-b1-erp-mock → main) | `pytest -v tests/test_erp_data.py` | `python -m app.tools.erp_seed && python -c "from app.tools import get_erp_data; print(get_erp_data('ORD-1001'))"` | Delete `app/`, `tests/`, update `.gitignore` and `requirements.txt`; revert is isolated (no dependencies yet) |

## Phase 1: Foundation & Package Bootstrap

- [ ] 1.1 Create `app/__init__.py` as an empty module initialization file
- [ ] 1.2 Create `app/tools/__init__.py` that exports `get_erp_data` for agent binding
- [ ] 1.3 Create `requirements.txt` with `sqlalchemy>=2.0`, `langchain-core>=0.1`, `pytest>=7.0`
- [ ] 1.4 Create `.gitignore` with entries for `data/erp_mock.db`, `__pycache__/`, `.pytest_cache/`, `*.pyc`

## Phase 2: ORM Model & Engine Layer

- [ ] 2.1 Create `app/tools/erp_data.py` with SQLAlchemy 2.0 declarative base and `ErpOrder` model
  - Columns: `order_id` (PK, String 32), `net_amount` (Numeric 12,2), `tax_amount` (Numeric 12,2), `total_amount` (Numeric 12,2), `region` (String 32), `status` (String 16)
- [ ] 2.2 Add lazy-initialized `_get_engine()` function reading `ERP_DB_PATH` env var (default: `data/erp_mock.db`)
- [ ] 2.3 Add `_get_session()` sessionmaker using the lazy engine
- [ ] 2.4 Implement `_fetch_order(order_id: str) → ErpOrder | None` using ORM `select().where()` with bound parameters (verify no SQL string interpolation)

## Phase 3: Seed Module & Dataset

- [ ] 3.1 Create `app/tools/erp_seed.py` with `SEED_ORDERS` constant (10 records minimum)
  - Coverage: 3 clean-match confirmed, 2 tax-mismatch, 2 wrong-region, 1 cancelled, 1 pending, 1 deliberately missing (ORD-9999 doc only)
  - Ensure region codes (`EU-ES`, `EU-DE`, `LATAM-CO`, etc.) and tax rates match proposal expectations
- [ ] 3.2 Implement `seed_database(engine)` using `session.merge()` over `SEED_ORDERS` for idempotent upsert
- [ ] 3.3 Add `__main__` entry point to `app/tools/erp_seed.py` for manual seeding: `python -m app.tools.erp_seed`
- [ ] 3.4 In `erp_data.py`, call `create_all()` and `seed_database()` on first engine initialization (verify idempotency)

## Phase 4: LangChain Tool Adapter

- [ ] 4.1 In `app/tools/erp_data.py`, add `@tool def get_erp_data(order_id: str) → dict` with LLM-ready docstring
  - Docstring must explain the lookup, list args, and mention the tool's use case (comparing invoices vs. ERP)
- [ ] 4.2 Validate `order_id` (trim whitespace, return not-found if empty)
- [ ] 4.3 Call `_fetch_order(order_id)` and map the result to a flat dict:
  - Hit: `{"found": True, "order_id": "...", "net_amount": float, "tax_amount": float, "total_amount": float, "region": "...", "status": "..."}`
  - Miss: `{"found": False, "order_id": "...", "message": "No ERP record found for order_id '...'."}` (no exception)
- [ ] 4.4 Verify the tool's `.name`, `.description`, and `.args_schema` are present for LLM function calling

## Phase 5: Test Infrastructure

- [ ] 5.1 Create `tests/__init__.py` as an empty module initialization file
- [ ] 5.2 Create `tests/conftest.py` with:
  - `tmp_path`-based pytest fixture that points `ERP_DB_PATH` to a temporary database
  - Fixture seeds the database using `seed_database()` and yields the engine
  - Fixture teardown cleans up the temp DB file
- [ ] 5.3 Update `app/tools/erp_data.py` to respect `ERP_DB_PATH` env var for test isolation

## Phase 6: Test Verification

- [ ] 6.1 Create `tests/test_erp_data.py` with:
  - **Unit: Hit Test** — Assert `get_erp_data("ORD-1001")` returns the seeded record with exact field values
  - **Unit: Miss Test** — Assert `get_erp_data("ORD-9999")` returns `{"found": False, ...}` with no exception
  - **Unit: Injection Test** — Call with `"ORD-1001' OR '1'='1"` and `"ORD-1001'; --"`, assert both return `found: False` and table is still queryable after
  - **Unit: Empty ID Test** — Assert `get_erp_data("")` and `get_erp_data("   ")` return `found: False` with no exception
  - **Unit: Flat Shape Test** — Assert hit result has exact keys, all scalar types, and `json.dumps(result)` succeeds
- [ ] 6.2 Add **Integration: Seed Idempotency Test** — Run `seed_database()` twice, assert row count is unchanged and data matches single run
- [ ] 6.3 Add **Integration: Tool Bindability Test** — Assert `get_erp_data.name`, `.args_schema` exist and `.invoke({"order_id": "ORD-1001"})` returns a dict without error
- [ ] 6.4 Run `pytest -v tests/test_erp_data.py` and verify all tests pass (add to CI later if needed)

## Implementation Order Notes

**Phase 1** (bootstrap) must complete first — the remaining phases depend on the package structure and dependencies.

**Phase 2** and **Phase 3** are **interdependent but parallel-safe**: the ORM model and seed data can be written in either order; ensure that `seed_database()` is called after `create_all()` to guarantee the schema exists before inserting rows.

**Phase 4** (tool adapter) depends on Phase 2 (the `_fetch_order` function) but is independent of Phase 3; however, for a working integration, Phase 3 should be complete.

**Phase 5** and **Phase 6** (tests) depend on all of Phases 1–4. Write test infrastructure before writing test cases.

**Critical implementation constraint** (Spec Req: Parametrized Query Execution):
- All SQL in `_fetch_order()` MUST use ORM-bound parameters or `text(...).bindparams()`. Verify by code review: no f-strings, no `.format()`, no `+` concatenation with `order_id`.

**Critical implementation constraint** (Spec Req: Deterministic Not-Found):
- `get_erp_data()` MUST **never raise an exception** for missing or malformed `order_id`. Return the not-found dict instead.

**Seed dataset region & tax rates** (Design note):
- MUST be re-confirmed against F-B2's `calculate_tax_discrepancy(amount, region)` at integration time.
- Document the regions and rates as comments in `SEED_ORDERS`.

---

## Verification Checklist (Per Spec & Design)

**Before marking Phase complete, verify:**

- ✓ Tool is importable: `from app.tools import get_erp_data`
- ✓ Tool has `__doc__`, `name`, `args_schema` (LangChain introspection)
- ✓ Hit path returns exact flat dict with scalar values only
- ✓ Miss path returns not-found dict with `found: False`
- ✓ SQL injection payloads are treated as literals, not syntax
- ✓ Seeding is idempotent (row count unchanged on re-run)
- ✓ All tests pass: `pytest -v tests/test_erp_data.py`
- ✓ No hardcoded paths; `ERP_DB_PATH` is configurable
- ✓ `Decimal` math is preserved in the ORM; `float()` conversion happens only at tool boundary for JSON safety
- ✓ `.gitignore` prevents accidental DB file commits
