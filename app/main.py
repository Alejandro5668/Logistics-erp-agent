"""ASGI entrypoint: `uvicorn app.main:app --reload`.

Deliberately calls `create_app()` with no overrides — the production path.
`Depends(get_agent)` resolves a real provider (`AGENT_MODEL` / `DEFAULT_MODEL`
via `build_agent()`) at the first request, which requires provider
credentials to be configured in the environment. Tests never import this
module; they build their own app via `app.api.app.create_app()` and override
`get_agent` / `get_thread_registry` directly (see `tests/test_api_endpoints.py`).
"""

from __future__ import annotations

from app.api.app import create_app

app = create_app()
