"""`create_app()` factory (design.md "File Changes" table): wires the F-B6
chat routes and PR 1's centralized exception handlers into one FastAPI app.

`app/main.py` is the process-wide ASGI entrypoint that imports `app` from
there via this factory. Tests build their own app instance through
`create_app()` and override `Depends(get_agent)` / `Depends(get_thread_registry)`
per-test (`app.dependency_overrides`) — never against a shared module-level
instance, so one test's scripted model/registry can never leak into another.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import EXCEPTION_HANDLERS
from app.api.routes.chat import router as chat_router


def create_app() -> FastAPI:
    """Build a fresh FastAPI app: PR 1's `ProviderUnavailableError` /
    `AgentExecutionError` handlers registered first (so they exist before
    any request can be routed), then the `/chat` and `/chat/sync` routes."""
    app = FastAPI(title="Logistics ERP Agent API")

    for exc_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exc_type, handler)

    app.include_router(chat_router)

    return app
