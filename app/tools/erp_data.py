"""Mock ERP data-access layer.

SQLAlchemy 2.0 declarative model and query layer for looking up logistics
orders in the (mocked) ERP system, plus the LangChain tool adapter (added in
a later section of this module) that exposes the lookup to the agent.

Two responsibilities live in this file on purpose (see design.md): the ORM
query layer (schema + `_fetch_order`) and the tool-adapter layer (LLM-facing
contract). They change for different reasons, but there is exactly one
entity and one data source, so a full ports-and-adapters split would be
speculative per the architecture-patterns Decision Gates.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import String, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import Numeric

DEFAULT_ERP_DB_PATH = "data/erp_mock.db"


class Base(DeclarativeBase):
    """Declarative base for all ERP mock models."""


class ErpOrder(Base):
    """A single ERP order record (the mock ERP's only table)."""

    __tablename__ = "erp_orders"

    order_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    region: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def _get_erp_db_path() -> str:
    """Read the configured ERP database path, honoring ERP_DB_PATH at call time."""
    return os.environ.get("ERP_DB_PATH", DEFAULT_ERP_DB_PATH)


def _get_engine() -> Engine:
    """Lazily build (and cache) the SQLAlchemy engine for the mock ERP database.

    Deliberately lazy: building the engine at import time would create the
    database file as a side effect of importing this module and would freeze
    ERP_DB_PATH before tests get a chance to override it.
    """
    global _engine, _session_factory
    if _engine is None:
        db_path = _get_erp_db_path()
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(_engine)

        # Imported lazily to avoid a hard import-time dependency cycle
        # (erp_seed imports ErpOrder from this module).
        from app.tools.erp_seed import seed_database

        seed_database(_engine)
        _session_factory = sessionmaker(bind=_engine)
    return _engine


def _reset_engine_cache() -> None:
    """Drop the cached engine/session factory so the next call rebuilds them.

    Test-only escape hatch: tests point ERP_DB_PATH at a fresh tmp_path
    database per test and must not reuse a previously cached engine.
    """
    global _engine, _session_factory
    _engine = None
    _session_factory = None


def _get_session() -> Session:
    """Return a new session bound to the lazily-initialized engine."""
    _get_engine()
    assert _session_factory is not None
    return _session_factory()


def _fetch_order(order_id: str) -> Optional[ErpOrder]:
    """Look up a single ERP order by its order_id using a bound parameter.

    Returns None if no row matches. Never raises for a missing/malformed id.
    The `where` clause below binds `order_id` as a parameter (ORM `select()`);
    no string interpolation or concatenation is used anywhere in this query.
    """
    with _get_session() as session:
        statement = select(ErpOrder).where(ErpOrder.order_id == order_id)
        return session.scalars(statement).first()


def _to_flat_dict(order: ErpOrder) -> dict:
    """Map an ErpOrder row to a flat, JSON-serializable dict (found case)."""
    return {
        "found": True,
        "order_id": order.order_id,
        "net_amount": float(order.net_amount),
        "tax_amount": float(order.tax_amount),
        "total_amount": float(order.total_amount),
        "region": order.region,
        "status": order.status,
    }


def _not_found(order_id: str) -> dict:
    """Build the deterministic not-found result for a missing/malformed id."""
    return {
        "found": False,
        "order_id": order_id,
        "message": f"No ERP record found for order_id '{order_id}'.",
    }


@tool
def get_erp_data(order_id: str) -> dict:
    """Look up a logistics order in the ERP by its order ID.

    Use this before comparing an invoice against the ERP. Returns the order's
    net, tax and total amounts, its region and its status.

    Args:
        order_id: The ERP order identifier, e.g. "ORD-1001".
    """
    cleaned_order_id = (order_id or "").strip()
    if not cleaned_order_id:
        return _not_found(order_id)

    order = _fetch_order(cleaned_order_id)
    if order is None:
        return _not_found(order_id)

    return _to_flat_dict(order)
