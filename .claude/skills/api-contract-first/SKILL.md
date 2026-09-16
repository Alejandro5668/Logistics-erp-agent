---
name: api-contract-first
description: "Trigger: contrato API, OpenAPI, generar tipos TypeScript, openapi-typescript, sincronizar frontend backend. Keep FastAPI's OpenAPI spec and the Next.js TS client in sync as the single source of truth."
license: Apache-2.0
metadata:
  author: "Johan-Campo"
  version: "1.0"
---

## Activation Contract

Load when designing or changing any FastAPI endpoint/Pydantic schema that the Next.js frontend consumes, or when generating/updating TypeScript types from the backend's OpenAPI spec.

## Hard Rules

- Every request/response shape is a named Pydantic model — never a bare `dict` or untyped `Any` for a schema the frontend will consume.
- The Pydantic model is the source of truth for the contract; FastAPI's auto-generated OpenAPI spec is the artifact both sides read — never a separate hand-written doc.
- After any Pydantic schema change (field added/removed/renamed, type changed), regenerate the frontend's TS types from the OpenAPI spec (`openapi-typescript`) before writing/consuming the frontend call for it.
- Never hand-write a TS interface duplicating a backend schema — it will drift; only generated types are trusted.
- Breaking changes (removing/renaming a field, changing a type or a status code's shape) must be agreed with whoever owns the other side before merging — treat it like breaking a public API, not an internal refactor.
- Additive, backward-compatible changes (a new optional field) don't require the other side to change anything immediately.

## Decision Gates

| Situation | Action |
|---|---|
| New endpoint or field needed by the frontend | Define/change the Pydantic model first, regenerate TS types, then write the frontend code against the generated types |
| Frontend needs a shape the backend doesn't expose yet | Do not invent a client-side type/mock — get the backend schema changed first |
| Removing/renaming a field or endpoint | Coordinate with the other side before merging; treat as a breaking contract change |
| TS build fails after a backend schema change | The contract is working as intended — fix the frontend call, don't bypass with `any` |

## Execution Steps

1. Define/update the Pydantic request/response model in FastAPI for the endpoint.
2. Regenerate the OpenAPI spec (automatic on FastAPI startup) and re-run `openapi-typescript` to refresh the frontend's generated types.
3. Write/update the frontend call using the freshly generated types — never widen a type with `any` to force a mismatch to compile.
4. If the change is breaking, confirm with whoever owns the other side before merging.

## Output Contract

State which Pydantic model(s) changed, whether the change is additive or breaking, and confirm the frontend's generated TS types were regenerated before the frontend code was written/changed.

## References

- `fastapi-backend-architecture` skill — where these Pydantic schemas live (router layer boundary).
- `typescript` skill — TS conventions for consuming the generated client types.
