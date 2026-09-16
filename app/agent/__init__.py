"""Agent package.

Re-exports `build_agent` (and the wiring constants tests assert on) here so
callers can do `from app.agent import build_agent` without reaching into
`app/agent/core.py` (mirrors `app/tools/__init__.py` and
`app/security/__init__.py`).
"""

from app.agent.core import AGENT_TOOLS, DEFAULT_MODEL, build_agent

__all__ = ["build_agent", "AGENT_TOOLS", "DEFAULT_MODEL"]
