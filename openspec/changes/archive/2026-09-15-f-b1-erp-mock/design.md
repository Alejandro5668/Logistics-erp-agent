# Design: F-B1 — Mock ERP Data Layer (`get_erp_data`)

## Technical Approach

Two thin layers, no ports/adapters ceremony:

1. **Query layer** (`app/tools/erp_data.py`): SQLAlchemy 2.0 declarative model `ErpOrder`, a lazily
   built `Engine`/`sessionmaker`, and one private function `_fetch_order(order_id) -> ErpOrder | None`
   using `select(...).where(ErpOrder.order_id == order_id)` — bound parameters by construction.
2. **Tool-adapter layer** (same file, below): `@tool def get_erp_data(order_id: str) -> dict`, which
   owns the LLM-facing docstring and maps the ORM row to a flat, JSON-safe dict.
3. **Seed layer** (`app/tools/erp_seed.py`): the dataset constant + an idempotent `seed_database()`,
   runnable as `python -m app.tools.erp_seed` and reusable as a pytest fixture.

Per `architecture-patterns` Decision Gates the signals are one entity, one integration, no invariants,
no read/write divergence → **plain layered code**, not Hexagonal; an `ErpRepositoryPort` for a single
mock source is speculative (`solid-principles`: YAGNI/KISS). The split that *is* justified is SRP:
schema changes hit the query layer, LLM-contract changes hit the tool adapter, demo-data changes hit
the seed module — three reasons to change, three units.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| SQL construction | ORM `select()` with a Python-value `where` clause | `text(f"... '{order_id}'")`, raw `sqlite3` | Bound params are structural, not a review habit; a `'; DROP`-bearing id is just a literal that misses |
| Structure | 2 layers in 1 file + separate seed module | Repository port + service + adapter | One entity/one source; extra interfaces add indirection without reducing change-risk |
| DB location | `ERP_DB_PATH` env var, default `data/erp_mock.db` | Hardcoded path; in-memory only | Tests bind a `tmp_path` DB; demo keeps a stable file; honors the proposal's recorded assumption |
| Engine lifetime | Module-level lazy `_get_engine()` cached after first call | Engine at import time | Import-time engine creates a file just by importing the tool and freezes the env var before tests set it |
| Money type | `Numeric(12, 2)` in the model, `float()` at the tool boundary | `Float` columns | `Decimal` keeps seeded cents exact for F-B2's discrepancy math; the dict must stay JSON-serializable for function calling |
| Not-found | `{"found": False, "order_id": ..., "message": ...}` | Return `None`; raise `OrderNotFound` | The LLM must be able to *read* the miss and reason about it; an exception aborts the ReAct step |
| Seeding | `session.merge()` over a constant list, `create_all()` first | Plain `INSERT`; Alembic migrations | `merge()` is upsert-by-PK → re-running is a no-op; migrations are overkill for a disposable mock |

## Data Flow

    create_agent ──(function call)──> @tool get_erp_data(order_id)
                                             │ 1. validate/trim str
                                             ▼
                                      _fetch_order()  ──select().where()──> SQLite
                                             │                                 ▲
                                             ▼ ErpOrder | None                 │
                                      flat dict (found / not found)     seed_database()
                                             │                          (idempotent merge)
                                             ▼
                                        LLM context

## File Changes

| File | Action | Description |
|---|---|---|
| `app/__init__.py`, `app/tools/__init__.py` | Create | Package bootstrap (first code in repo) |
| `app/tools/erp_data.py` | Create | Model + engine/session + `_fetch_order` + `@tool get_erp_data` |
| `app/tools/erp_seed.py` | Create | `SEED_ORDERS` constant + `seed_database(engine)` + `__main__` entry |
| `tests/conftest.py` | Create | First pytest runner setup: `tmp_path` DB fixture, seeds it, points the module engine at it |
| `tests/test_erp_data.py` | Create | Hit / miss / injection-style id |
| `requirements.txt` | Create | `sqlalchemy`, `langchain-core`, `pytest` |
| `.gitignore` | Create | Ignore `data/*.db`, `__pycache__/` |

## Interfaces / Contracts

```python
class ErpOrder(Base):
    __tablename__ = "erp_orders"
    order_id:     Mapped[str]     = mapped_column(String(32), primary_key=True)
    net_amount:   Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax_amount:   Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    region:       Mapped[str]     = mapped_column(String(32))   # e.g. "EU-ES", "EU-DE", "LATAM-CO"
    status:       Mapped[str]     = mapped_column(String(16))   # confirmed | pending | cancelled

@tool
def get_erp_data(order_id: str) -> dict:
    """Look up a logistics order in the ERP by its order ID.

    Use this before comparing an invoice against the ERP. Returns the order's
    net, tax and total amounts, its region and its status.

    Args:
        order_id: The ERP order identifier, e.g. "ORD-1001".
    """
```

Hit: `{"found": True, "order_id": "ORD-1001", "net_amount": 1000.0, "tax_amount": 210.0,
"total_amount": 1210.0, "region": "EU-ES", "status": "confirmed"}`
Miss: `{"found": False, "order_id": "<echoed input>", "message": "No ERP record found for order_id '<id>'."}`
Flat by design (proposal risk: shape churn at F-B2/F-B5 integration) — no nesting, no ORM objects.

## Seed Dataset (10 records)

| Case | Coverage |
|---|---|
| Clean match | 3 confirmed orders whose `tax_amount` matches the region's rate exactly |
| Tax mismatch | 2 confirmed orders where tax is over/under the regional rate (F-B2 fuel) |
| Wrong region | 2 orders whose region does not match the expected tax band |
| Cancelled / pending | 2 orders (1 each) — status must block naive adjustment |
| Missing order | `ORD-9999` documented as deliberately **not** seeded, for the miss test |

No PII, no salary, no names — F-B4's guardrail does not exist yet (proposal out-of-scope).

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | `_fetch_order` hit/miss against a seeded `tmp_path` DB | pytest fixture seeds, asserts field values (fails if the `where` clause breaks) |
| Unit | Injection-style ids: `ORD-1001'; DROP TABLE erp_orders; --`, `' OR '1'='1` | Assert `found is False` **and** the table still answers afterwards |
| Unit | Flat return shape + `float` types on hit and miss | Assert exact key set; `json.dumps(result)` must not raise |
| Integration | Seed idempotency | Run `seed_database()` twice; row count unchanged |
| Integration | Tool is bindable | Assert `get_erp_data.name`/`.args_schema` exist and `.invoke({"order_id": ...})` works |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary. The one security surface (SQL injection) is structurally handled by the
ORM bound-parameter decision above and verified by a dedicated test.

## Migration / Rollout

No migration required. `create_all()` builds the schema on first run; the DB file is disposable and
gitignored. Rollback = delete the new files per the proposal.

## Open Questions

- [ ] None blocking. Region codes (`EU-ES`, `EU-DE`, `LATAM-CO`) and their tax rates are chosen here
      and MUST be re-confirmed against F-B2's `calculate_tax_discrepancy(amount, region)` at integration.
