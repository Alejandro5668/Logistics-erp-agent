"""Agent-facing RAG package.

Re-exports the retrieval tool here so agent wiring can do
`from app.rag import search_regulations` without reaching into individual
modules.
"""

from app.rag.store import search_regulations

__all__ = ["search_regulations"]
