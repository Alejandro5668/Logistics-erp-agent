---
name: fastapi-backend-architecture
description: "Trigger: FastAPI, backend Python, arquitectura backend Python, router service repository, Pydantic, SQLAlchemy async. Structure FastAPI/Python backend logic in readable, low-complexity layers."
license: Apache-2.0
metadata:
  author: "Johan-Campo"
  version: "1.0"
---

## Activation Contract

Load when writing or reviewing backend logic in FastAPI/Python: routers/endpoints, services, repositories, Pydantic schemas, or SQLAlchemy models. Applies to Volarte and any FastAPI backend in this workspace.

## Hard Rules

- One responsibility per layer: router parses + validates input via Pydantic and calls a service; service holds business logic; repository only talks to the DB (SQLAlchemy) or external APIs (AI providers, R2, Pusher). Never let business logic leak into a router, or DB/HTTP calls leak into a service.
- Validate all external input (request body, query/path params, env vars) with Pydantic models at the boundary, before it reaches a service.
- Raise typed/domain exceptions from services (e.g. `NotFoundError`, `ValidationError`); never raise raw strings or format HTTP responses inside a service.
- Route all errors through one centralized FastAPI exception handler (`@app.exception_handler`); never per-endpoint try/except formatting responses.
- Inject repositories/services/external providers via `Depends()`; never instantiate a concrete class inline inside business logic (Dependency Inversion).
- Everything async end-to-end: async routers, async SQLAlchemy sessions; wrap any blocking/sync call with `run_in_threadpool` instead of calling it directly inside async code.
- Avoid nesting beyond 2 levels of if/try; use guard clauses and early returns instead.
- Name functions by what they return or do (`get_producto_by_id`), never by mechanism (`db_query_1`).
- If a function needs a comment to explain what it does, split it into smaller named functions instead.

## Decision Gates

| Situation | Action |
|---|---|
| New endpoint | router -> service -> repository; no business logic in the router |
| External input | Validate with a Pydantic schema before calling the service |
| Error from a service | Raise a typed exception; let the centralized exception handler convert it to an HTTP response |
| Need a DB session, repository, or AI provider in a router/service | Inject via `Depends()`, never construct it inline |
| Function hard to read in one pass | Extract a named helper instead of adding comments |
| Calling a sync-only library from async code | Wrap it with `run_in_threadpool`, never block the event loop |

## Execution Steps

1. Identify which layer the change belongs to before writing code.
2. Validate external input with a Pydantic schema at the entry point.
3. Keep business logic only in services; keep repositories thin.
4. Raise typed exceptions from services; let the centralized exception handler format the response.
5. Inject dependencies via `Depends()`; never instantiate concrete implementations inside business logic.
6. Check function length/nesting; split anything over ~30-40 lines or nested past 2 levels.

## Output Contract

State which layer each piece of added/changed logic belongs to. Flag any logic misplaced across layers, any blocking call inside async code, and any function that should be split for readability.

## References

- `architecture-patterns` skill — system-level structure (Hexagonal/DDD) this layering implements concretely.
- `solid-principles` skill — class/function-level principles (DIP via `Depends()`, SRP per layer) this skill applies.
- `pytest` skill — how to test each layer.
- `nodejs-backend-architecture` skill — equivalent layering for the Next.js/TS side of this same project.
