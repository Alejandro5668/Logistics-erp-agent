"""Security guardrail package: role-scoped data protection + prompt-injection
defense (F-B4).

Re-exports the pure core here so callers can do
`from app.security import Role, inspect_input` without reaching into
individual modules (mirrors `app/tools/__init__.py`).

PR-1 scope only: `build_security_middleware` does not exist yet
(`app/security/middleware.py` ships in a follow-up PR once F-B5 needs the
LangChain adapter) and is intentionally NOT exported here.
"""

from app.security.guardrail import inspect_input, inspect_output
from app.security.roles import Role, resolve_role

__all__ = [
    "Role",
    "resolve_role",
    "inspect_input",
    "inspect_output",
]
