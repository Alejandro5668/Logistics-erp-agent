"""Agent-facing tools package.

Re-exports tools here so agent wiring can do `from app.tools import get_erp_data`
without reaching into individual modules.

`search_regulations` (F-B3) is NOT re-exported here on purpose — it lives in
`app.rag.store`; `app/agent/core.py` imports it from there directly, keeping
package boundaries honest (see design.md footnote 1).
"""

from app.tools.actions import create_erp_adjustment, notify_human
from app.tools.erp_data import get_erp_data
from app.tools.tax_discrepancy import calculate_tax_discrepancy

__all__ = [
    "get_erp_data",
    "calculate_tax_discrepancy",
    "create_erp_adjustment",
    "notify_human",
]
