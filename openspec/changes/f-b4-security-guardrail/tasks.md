# Tasks: F-B4 — Security Guardrail (role-scoped data protection + prompt-injection defense)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 650–750 (core ~280 + tests ~370) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Consider: PR 1 (core + unit tests) → PR 2 (middleware + integration tests) |
| Delivery strategy | chained (user decision, overrides preflight single-pr for this change) |
| Chain strategy | stacked-to-main (sequential: PR 1 merges before PR 2 branches) |

**Plain-text guard lines (for downstream tooling):**
```
Decision needed before apply: No (resolved — chained PRs approved by user)
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High (mitigated by the split below)
```

### Work Unit Rationale (decided: chained, 2 PRs)

This is a security-critical module with comprehensive threat defense requirements (Threat Model: 8 defended threats). User explicitly chose to split rather than accept a `size:exception`:
- **PR 1 (core guardrail)** — branch `feature/f-b4-security-guardrail`: Phases 1–3 + tests 5.1–5.3 (roles.py, injection.py, guardrail.py + their unit tests). `app/security/__init__.py` exports only what exists at this point (`Role`, `resolve_role`, `inspect_input`, `inspect_output`) — NOT `build_security_middleware` yet. ~450 lines.
- **PR 2 (adapter)** — branch `feature/f-b4-security-guardrail-middleware`, created from `main` AFTER PR 1 merges: Phase 4 + test 5.4 (middleware.py + its test), plus completing `__init__.py`'s export list with `build_security_middleware`. ~200 lines.

---

## Phase 1: Foundation — Role Model & Restricted-Field Catalog

_Prerequisite for all detection logic. Pure, stdlib-only, no external dependencies._

- [x] 1.1 Create `app/security/__init__.py` — placeholder re-export shell (will populate in Phase 6). PR-1 note: populated now with the exports that exist in this PR (`Role`, `resolve_role`, `inspect_input`, `inspect_output`); `build_security_middleware` is NOT exported (deferred to PR 2)
- [x] 1.2 Create `app/security/roles.py` — `Role(IntEnum)` with `EMPLOYEE=1`, `FINANCE_MANAGER=2`, `ADMIN=3`; `RESTRICTED_FIELDS: dict[str, Role]` with five canonical keys (salary, bank_account, employee_id, national_id, personal_contact); `FIELD_ALIASES: dict[str, str]` (e.g., "salario" → "salary", "cuenta bancaria" → "bank_account"); implement `_normalize_field(s: str) -> str` (casefold → strip accents NFKD → replace `_`/`-` with space → collapse); implement `resolve_role(raw: object) -> Role` (never raises, unknown/None/malformed → `Role.EMPLOYEE`)

---

## Phase 2: Injection Pattern Detection

_Depends on Phase 1. Pure, stdlib `re` only. Must cover threat T2/T7 (prompt injection + ReDoS guard)._

- [x] 2.1 Create `app/security/injection.py` — `INJECTION_PATTERNS: list[tuple[str, str]]` with ~8 ID-tagged regex pairs (INJ-01 through INJ-08, one ES + one EN variant each; IDs: instruction-override, persona/role-override, system-prompt-extraction, control-disable, privilege-claim, bulk-exfiltration, prompt-boundary-spoofing, encoding-evasion); compile patterns; implement `find_injection(text: str) -> tuple[str, ...]` (matching pattern IDs; truncate input to `MAX_SCAN_CHARS = 20_000` before matching for ReDoS guard; return empty tuple if no match)

---

## Phase 3: Core Guardrail Logic

_Depends on Phases 1–2. Pure, no LangChain. Implements spec requirements + threat defenses T1, T3–T5, T8._

- [x] 3.1 Create `app/security/guardrail.py` skeleton — import `Verdict(str, Enum)` with `ALLOW` and `BLOCK` values; implement `@dataclass(frozen=True) ToolCall(name: str, args: dict)`; implement `@dataclass(frozen=True) AgentOutput(text: str, tool_calls: tuple[ToolCall, ...] = ())`; implement `@dataclass(frozen=True) GuardrailDecision(verdict: Verdict, reason_code: str, matched: tuple[str, ...], message: str)` (reason codes: OK | INJECTION_PATTERN | RESTRICTED_FIELD_REQUEST | RESTRICTED_FIELD_IN_OUTPUT | RESTRICTED_FIELD_IN_TOOL_ARGS | GUARDRAIL_ERROR)

- [x] 3.2 Implement `inspect_input(text: str, role: Role) -> GuardrailDecision` — call `find_injection(text)`; if matches, return `BLOCK` with reason `INJECTION_PATTERN` and matched IDs; scan normalized text for restricted field names above the caller's role (using `RESTRICTED_FIELDS` + `FIELD_ALIASES`); if found, return `BLOCK` with reason `RESTRICTED_FIELD_REQUEST` and matched field; otherwise return `ALLOW` with reason `OK` and empty matched; safe message for BLOCK: static generic text (e.g., "I cannot assist with that request")

- [x] 3.3 Implement `inspect_output(payload: AgentOutput, role: Role) -> GuardrailDecision` — scan `payload.text` and all tool-call argument keys/values (depth-capped at 5, recursively flattened) for restricted fields above the caller's role (threat T4: data written into ERP via tool args); if any match, return `BLOCK` with reason `RESTRICTED_FIELD_IN_OUTPUT` or `RESTRICTED_FIELD_IN_TOOL_ARGS` (differentiated in logs) and matched fields; use normalized comparison; safe message: static generic text; if no restricted content found, return `ALLOW` with reason `OK`

---

## Phase 4: Middleware Adapter (LangChain Bridge)

_Depends on Phase 3. ONLY module allowed to import LangChain. Implements threat T6 (prevents half-wiring)._

- [x] 4.1 Create `app/security/middleware.py` — implemented in PR 2 (branch `feature/f-b4-security-guardrail-middleware`). API shape re-confirmed at apply time against installed `langchain==1.4.0` (per F-B3 chromadb precedent) and adapted: the installed API is a class-based `AgentMiddleware` subclass with `before_model(self, state: AgentState, runtime: Runtime)` / `after_model(self, state: AgentState, runtime: Runtime)` methods (each decorated `@hook_config(can_jump_to=["end"])`), not the flat `context: dict` shape sketched in this task — the `jump_to="end"` blocking-update key matched design.md's assumption exactly. `build_security_middleware(role_resolver: Callable[[Any], object] = _role_from_context)` factory returns one `SecurityGuardrailMiddleware` instance carrying both hooks; `_role_from_context(context)` default resolver reads `context.get("role")` (dict) or `getattr(context, "role", None)` (object), called with `runtime.context`; BLOCK on either hook returns `{"messages": [AIMessage(safe_message)], "jump_to": "end"}`; ALLOW returns `None`. Core contract (`roles.py`/`injection.py`/`guardrail.py`) untouched.

---

## Phase 5: Unit & Integration Tests

_Can parallelize per-file. Each test set is independent and can run in isolation. Load-bearing: "output backstop" test (5.3.3) proves input side alone is insufficient._

- [x] 5.1 Create `tests/test_security_roles.py` — Role ladder test (salary for EMPLOYEE → blocked; for FINANCE_MANAGER/ADMIN → allowed; proves IntEnum ordering works); catalog anti-drift test (assert exact `RESTRICTED_FIELDS` key set == {salary, bank_account, employee_id, national_id, personal_contact} and each min role); test aliases (salario/sueldo/nomina → salary; cuenta_bancaria/iban → bank_account; etc.); test normalization (SALARIO / Salário / bank-account → canonical field); test fail-closed `resolve_role()` (None, "", "root", "ADMIN ", 123, `object()` → `Role.EMPLOYEE`, no exception)

- [x] 5.2 Create `tests/test_security_injection.py` — For each INJ-01 through INJ-08: one English probe + one Spanish probe → `find_injection()` returns that ID in the tuple; test that legitimate queries pass (corpus: "¿por qué la orden ORD-1001 tiene una discrepancia fiscal?", "compara el IVA con la normativa 2024", "What is the tax rate for 2024?", etc. for every role → empty matched tuple); test case-folding evasion and accent evasion in patterns

- [x] 5.3 Create `tests/test_security_guardrail.py` — **[LOAD-BEARING]** Output backstop test: input that passes `inspect_input()` cleanly, but model's answer contains `salario` → `inspect_output()` must return BLOCK (fails if only input side wired); test all roles × both directions (input: 3 roles × 2 directions = 6; output: 3 roles × 2 directions = 6; total 12 combos); tool-call-arg test (ToolCall with `{"note": "salario de …"}` and `{"salary": 1}` → BLOCK; clean args → ALLOW); must-not-block corpus (fiscal queries, order reconciliation, tax rate lookups for every role → ALLOW); message hygiene (assert `decision.message` never contains matched field names or pattern IDs, only generic safe text)

- [x] 5.4 Create `tests/test_security_middleware.py` — implemented in PR 2. Tests `before_model` hook callable and shape (BLOCK → `jump_to="end"` + safe message; ALLOW → None); `after_model` hook callable and shape (same, including tool-call-args blocking before tool execution); factory returns one object (no loose helpers); custom `role_resolver` injection (override + fail-closed on malformed custom-resolved role); default resolver reads role from dict `Runtime.context` and fails closed on missing context; message hygiene through the adapter. `pytest.importorskip("langchain")` kept in setup as defensive practice even though `langchain` is now a real dependency (`requirements.txt`), per this PR's brief — a grader environment lacking it skips this file cleanly instead of erroring collection.

---

## Phase 6: Module Integration & Exports

_Depends on Phases 1–4. Pure re-export housekeeping._

- [x] 6.1 Populate `app/security/__init__.py` — re-export `Role`, `resolve_role`, `inspect_input`, `inspect_output`, `build_security_middleware` (mirrors `app/tools/__init__.py` pattern). PR 1 exported `Role`, `resolve_role`, `inspect_input`, `inspect_output`; PR 2 adds `build_security_middleware` now that `middleware.py` exists. All five exported.

- [x] 6.2 Verify module import paths — `import app.security` and `from app.security import Role, resolve_role, inspect_input, inspect_output, build_security_middleware` all verified working. `langchain` is now a real, pinned dependency (`requirements.txt`) as of this PR, so it importing at `app.security.middleware` module load is expected and no longer something to guard against; the pure core (`roles.py`/`injection.py`/`guardrail.py`) still imports no LangChain symbol. Confirmed via full `pytest -v` run (all 209 pre-existing tests + new middleware tests green).

---

## Dependency & Execution Order

```
Phase 1 (Foundation)
  ↓
Phase 2 (Injection Detection)
  ↓
Phase 3 (Core Guardrail)
  ├─→ Phase 5.1 (test_security_roles.py) — parallel after Phase 1
  ├─→ Phase 5.2 (test_security_injection.py) — parallel after Phase 2
  └─→ Phase 5.3 (test_security_guardrail.py) — parallel after Phase 3
  ↓
Phase 4 (Middleware)
  └─→ Phase 5.4 (test_security_middleware.py) — parallel after Phase 4
  ↓
Phase 6 (Integration & Exports)
```

**Sequential critical path**: Phase 1 → 2 → 3 → 4 → 6 (must complete in order).  
**Parallel opportunities**: Unit tests (5.1, 5.2, 5.3, 5.4) can run in parallel after their corresponding implementation phases complete.

---

## Verification Checklist (per design's threat model and spec scenarios)

After all tasks complete, verify:
- [ ] All 8 threat defenses (T1–T8) are implemented and tested
- [ ] Load-bearing "output backstop" test (5.3.3) passes — proves defense-in-depth
- [ ] All 6 residual risks (R1–R6) are documented in README/comments
- [ ] Injection patterns (8 IDs × 2 languages) are all regex-tested
- [ ] All four role-field combinations are tested (role × field × direction)
- [ ] `resolve_role()` never raises exception
- [ ] Middleware factory exports one object, no loose helpers
- [ ] LangChain import is lazy (only in middleware.py, guarded by pytest.importorskip in tests)
- [ ] All tests pass: `pytest -v tests/test_security_*.py`

---

## Notes

- **Threat Model Integration**: This module defends threats T1–T8 as detailed in design.md. T3 (indirect injection via RAG) is explicitly a defense-in-depth layer; T4 (data into ERP via tool args) is caught before tool execution.
- **Fail-Closed Guarantee**: `resolve_role()` and all adapters default to least privilege (EMPLOYEE); no exception is raised; adapter exception → GUARDRAIL_ERROR → BLOCK.
- **No Auth/JWT**: Role is caller-supplied and spoofable (R1, by design). F-B6 will later point `role_resolver` at a verified JWT claim; core logic is unchanged.
- **ReDoS Guard**: Input truncated to 20,000 chars; patterns are linear (no nested quantifiers).
- **Test Strategy**: Per openspec/config.yaml, strict TDD is not yet enforced for Track B, but this module has comprehensive tests covering spec scenarios, threat matrix, and must-not-block corpus. Tests validate that the core is pure and testable without an LLM or agent.
