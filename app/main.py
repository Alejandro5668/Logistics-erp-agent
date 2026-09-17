"""ASGI entrypoint: `uvicorn app.main:app --reload`.

Deliberately calls `create_app()` with no overrides — the production path.
`Depends(get_agent)` resolves a real provider (`AGENT_MODEL` / `DEFAULT_MODEL`
via `build_agent()`) at the first request, which requires provider
credentials to be configured in the environment. Tests never import this
module; they build their own app via `app.api.app.create_app()` and override
`get_agent` / `get_thread_registry` directly (see `tests/test_api_endpoints.py`).

`load_dotenv()` runs first so a `.env` file (see `.env.example`) is loaded
before `AGENT_MODEL` and friends are read. No `.env`? No-op, falls back to
real environment variables.

The optional `/demo` static browser UI (`web/`) is mounted here, not inside
`create_app()`: this module is the one place already documented as
test-free, so a demo-only concern mounted here can never leak into the
tested application factory. Absent `web/` (e.g. a deploy that strips it),
this is a no-op.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.api.app import create_app  # noqa: E402 — must follow load_dotenv()

app = create_app()

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if _WEB_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/demo", StaticFiles(directory=_WEB_DIR, html=True), name="demo")
