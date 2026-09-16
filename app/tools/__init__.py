"""Agent-facing tools package.

Re-exports tools here so agent wiring can do `from app.tools import get_erp_data`
without reaching into individual modules.
"""

from app.tools.erp_data import get_erp_data
from app.tools.tax_discrepancy import calculate_tax_discrepancy

__all__ = ["get_erp_data", "calculate_tax_discrepancy"]
