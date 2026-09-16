# Archive Report: F-B4 — Security Guardrail

## Summary

Role-scoped data-protection and prompt-injection guardrail for the agent, delivered as **two
chained PRs** (user-approved split, since the single-PR estimate of 650–750 lines exceeded the
400-line review budget):

- **PR 1** ([#4](https://github.com/Alejandro5668/Logistics-erp-agent/pull/4), merged) — pure
  core: `app/security/roles.py`, `app/security/injection.py`, `app/security/guardrail.py`. No
  LangChain dependency.
- **PR 2** ([#5](https://github.com/Alejandro5668/Logistics-erp-agent/pull/5), merged) —
  `app/security/middleware.py`, the adapter wiring the pure core into `create_agent`'s
  `before_model`/`after_model` hooks. Added `langchain>=0.3` as a dependency for the first time
  in this repo.

## Final State

- All 18 tasks across both PRs complete (`tasks.md`).
- Both `sdd-verify` passes: PASS, 0 CRITICAL issues (`verify-report.md` for PR 1,
  `verify-report-pr2.md` for PR 2). Total of 4 non-blocking WARNINGs across both reports — all
  documentation-only (spec/design terminology drift, README limitation-surfacing gap) — no code
  defects.
- `pytest -v` on `main` after both merges: **228/228 passing** (69 pre-existing from F-B1/F-B2/F-B3
  + 140 core security tests + 19 middleware tests).
- Threat model: 8 threats defended (T1–T8), 6 residual risks explicitly documented, not hidden
  (most notably R1: role is client-supplied and spoofable in this prototype — no real auth yet).

## Notable Engineering Findings (real, not cosmetic)

1. **Bug caught during PR 1 development**: `resolve_role` originally stripped whitespace before
   matching, which would have resolved `"ADMIN "` (trailing space) to `Role.ADMIN` instead of
   failing closed to `Role.EMPLOYEE`. Fixed before merge; regression test added.
2. **API-shape drift confirmed at PR 2 apply time**: `design.md` sketched a flat
   `before_model(context: dict)` function shape; the installed `langchain==1.4.0` requires a
   class-based `AgentMiddleware` subclass with instance methods and `@hook_config`. Adapted
   faithfully to the design's *intent* (one object, `jump_to="end"` blocking key, per-invocation
   role resolution) without touching the PR 1 core contract — same precedent as F-B3's chromadb
   version drift.

## Spec Merge

`security-guardrail` is a new capability — full spec published to `openspec/specs/security-guardrail/spec.md`
(no prior version to delta against). One requirement was added during merge, reflecting what PR 2
actually delivered and PR 2's own verify pass confirmed (framework-agnostic core, single middleware
object) — not present in the original delta spec, since PR 2 didn't exist yet when the delta spec
was written.

## Consumers

`app/security/__init__.py` now exports `Role`, `resolve_role`, `inspect_input`, `inspect_output`,
and `build_security_middleware` — the complete guardrail surface. Ready for F-B5 (agent core) to
wire `build_security_middleware()` into `create_agent`'s middleware list, and for F-B6 (API) to
later repoint the default `role_resolver` at a verified identity claim (R1's stated remediation
path).

## Known Follow-ups (non-blocking, tracked here since no other backlog exists in this prototype)

- Surface the R1 spoofable-role limitation in the top-level `README.md` once the API (F-B6) exists
  and the limitation becomes user-facing, not just internal design documentation.
- `design.md`'s Dependency decision-table row still says "langchain is F-B5's to add" — stale
  relative to PR 2 actually adding it; cosmetic only, the real dependency list in
  `requirements.txt` is correct.
