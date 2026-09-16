"""Security guardrail package: role-scoped data protection + prompt-injection
defense (F-B4).

Re-exports the pure core AND the middleware adapter here so callers can do
`from app.security import Role, inspect_input, build_security_middleware`
without reaching into individual modules (mirrors `app/tools/__init__.py`).

Importing `build_security_middleware` from this package does not pull in
`langchain` at package-import time any more than importing
`app.security.middleware` directly would — the LangChain import lives in
that one module (`app/security/middleware.py`), never in `roles.py`,
`injection.py`, or `guardrail.py`.
"""

from app.security.guardrail import inspect_input, inspect_output
from app.security.middleware import build_security_middleware
from app.security.roles import Role, resolve_role

__all__ = [
    "Role",
    "resolve_role",
    "inspect_input",
    "inspect_output",
    "build_security_middleware",
]
