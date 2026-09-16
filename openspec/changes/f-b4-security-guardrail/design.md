# Design: F-B4 — Security Guardrail (role-scoped data protection + prompt-injection defense)

## Technical Approach

Same shape as F-B1/F-B2/F-B3: **deterministic pure core + thin adapter**, escalated by one notch
because the adapter's framework boundary is a security boundary.

| Module | Responsibility | Imports |
|---|---|---|
| `app/security/roles.py` | `Role` ladder, `RESTRICTED_FIELDS` catalog, aliases, `resolve_role()` | stdlib only |
| `app/security/injection.py` | `INJECTION_PATTERNS` (documented regex list), `find_injection()` | stdlib `re` only |
| `app/security/guardrail.py` | Pure core: `inspect_input`/`inspect_output` → `GuardrailDecision` | the two above |
| `app/security/middleware.py` | Adapter: `build_security_middleware()` for `create_agent` | LangChain (only here) |

`architecture-patterns` Decision Gates: one in-process concern, no data source, no read/write
divergence → **plain layered code**, not Hexagonal; no `DetectorPort`, no strategy registry
(`solid-principles`: YAGNI/KISS). The one split that *is* earned is SRP + the hard rule "the
domain layer has zero framework imports": catalog data, detection patterns, verdict logic and
framework glue each change for a different reason, and the core must be unit-testable with no
LLM, no agent and no `langchain` installed (only `langchain-core` is in `requirements.txt` today).

This **refines** the proposal's file list, which put `build_security_middleware()` inside
`guardrail.py`. Keeping it there would drag a LangChain import into the pure module and make the
core untestable without the framework. Everything else in the proposal's scope is unchanged.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Verdict set | `ALLOW` / `BLOCK` only, deny by default | `WARN`/`REDACT` tiers | A tier nobody consumes is speculative; per-field redaction is explicitly out of scope |
| Role model | `class Role(IntEnum)` `EMPLOYEE=1 < FINANCE_MANAGER=2 < ADMIN=3` | str enum + explicit allow-set per role | Visibility is a monotonic ladder; `role >= required` is one expression and a new field is a **data** edit, not a new branch (OCP) |
| Catalog shape | `RESTRICTED_FIELDS: dict[str, Role]` (canonical field → min role) + `FIELD_ALIASES: dict[str, str]` | Regex per field; role → field-set map | Decision 2's shape; DRY — aliases resolve to one canonical field, so the verdict rule exists once |
| Detection | Explicit compiled regex list, ~8 entries, each with an ID + one-line comment | ML/LLM classifier, NLP library, external API | Scope decision 5; a prototype guardrail must be auditable, offline, deterministic and fast |
| Input blocking | Block **before** the model runs (`before_model` hook) | Post-hoc filtering | Decision 3 — a blocked turn must cost zero tokens and reach no tool |
| Role transport | Explicit argument on every core function: `inspect_input(text, role)` | Implicit thread-local / global | Decision 4; keeps the core pure and the test matrix trivial |
| Role at the hook | `role_resolver` callable injected into the factory (default reads `context["role"]`) | Binding one `Role` into a process-lifetime middleware instance | The agent is built once but serves many callers; DIP — the resolver is the seam F-B6 later points at a JWT claim |
| Output payload | Core takes a framework-free `AgentOutput(text, tool_calls)`; the adapter maps `AIMessage` → it | Core accepts `AIMessage` | Keeps `langchain_core.messages` out of the domain; the mapping is the adapter's whole job |
| Normalization | casefold → strip accents (NFKD) → `_`/`-` → space → collapse | Raw `in` substring match | `Salario`, `salary`, `bank_account`, `cuenta bancaria` are one alias each, not four; also kills trivial casing evasion |
| Safe message | Static generic text; `matched`/`reason_code` stay in the decision object for logs | Echo the matched field/pattern | Echoing the trigger leaks the catalog and confirms the probe to an attacker |
| Failure mode | Unknown/absent/malformed role → `EMPLOYEE`; adapter exception → `BLOCK` (`GUARDRAIL_ERROR`) | Raise; default to ADMIN | Fail-closed to least privilege. The core itself never raises (F-B1/F-B2 convention) |
| Dependency | No new requirement; `langchain` is F-B5's to add. Adapter test uses `pytest.importorskip` | Pin `langchain` now | F-B4 only *defines* the hook contract; nothing runs an agent yet |

## Data Flow (middleware sequence)

    user turn ──> before_model ──> resolve_role(context) ──> inspect_input(text, role)
                                        │                          │
                                        │                     BLOCK│  {"messages":[AIMessage(safe)],
                                        │                          └──> "jump_to":"end"}  ── model never called
                                        ▼ ALLOW
                                      MODEL
                                        │
                                        ▼
                     after_model ──> AIMessage → AgentOutput(text, tool_calls)
                                        │
                                        ├── scan text        ──┐
                                        └── scan tool-call args┤──> inspect_output(payload, role)
                                                               │
                                        BLOCK ──> replace message + jump_to "end"  (tool never executes,
                                        ALLOW ──> tools / user                      ERP never written)

`after_model` runs **before** tool execution, so a `create_erp_adjustment(note="salario …")` call is
stopped on the way *in* to the ERP, not only on the way out to the user.

## Interfaces / Contracts

```python
# roles.py
class Role(IntEnum): EMPLOYEE = 1; FINANCE_MANAGER = 2; ADMIN = 3
RESTRICTED_FIELDS: dict[str, Role] = {
    "salary":           Role.FINANCE_MANAGER,   # salario, sueldo, nomina, payroll, compensation, bonus
    "bank_account":     Role.FINANCE_MANAGER,   # iban, cuenta bancaria, account number
    "employee_id":      Role.FINANCE_MANAGER,   # employee number, legajo
    "national_id":      Role.ADMIN,             # ssn, dni, nif, tax id
    "personal_contact": Role.ADMIN,             # home address, personal email, telefono
}
def resolve_role(raw: object) -> Role: ...      # never raises; unknown -> EMPLOYEE

# guardrail.py  (pure, no LangChain)
class Verdict(str, Enum): ALLOW = "ALLOW"; BLOCK = "BLOCK"

@dataclass(frozen=True)
class GuardrailDecision:
    verdict: Verdict
    reason_code: str          # OK | INJECTION_PATTERN | RESTRICTED_FIELD_REQUEST
                              # | RESTRICTED_FIELD_IN_OUTPUT | RESTRICTED_FIELD_IN_TOOL_ARGS
                              # | GUARDRAIL_ERROR
    matched: tuple[str, ...]  # pattern IDs or canonical field names — for logs, NOT for the user
    message: str              # safe, generic, reveals nothing

@dataclass(frozen=True)
class ToolCall:  name: str; args: dict
@dataclass(frozen=True)
class AgentOutput: text: str; tool_calls: tuple[ToolCall, ...] = ()

def inspect_input(text: str, role: Role) -> GuardrailDecision: ...
def inspect_output(payload: AgentOutput, role: Role) -> GuardrailDecision: ...

# middleware.py  (the ONLY module allowed to import langchain)
def build_security_middleware(role_resolver: Callable[[Any], object] = _role_from_context): ...
```

Input rule: BLOCK if any injection pattern matches **or** a restricted field is named whose
`RESTRICTED_FIELDS[field] > role`. Output rule: BLOCK if a restricted field above the caller's role
appears in the final text **or** in any tool-call argument (keys and values, recursively flattened,
depth-capped at 5). A field at or below the caller's role is ALLOW in both directions.

### Injection pattern list (explicit, ~8 — ES + EN, each ID-tagged)

`INJ-01` instruction override (`ignore previous instructions`, `olvida las instrucciones`) ·
`INJ-02` persona/role override (`you are now`, `actua como administrador`) ·
`INJ-03` system-prompt extraction (`reveal/show your system prompt`, `muestra tu prompt`) ·
`INJ-04` control disable (`disable the guardrail/filter`, `sin restricciones`, `bypass security`) ·
`INJ-05` privilege claim (`i am an admin`, `soy el administrador`) ·
`INJ-06` bulk exfiltration (`dump all fields/records`, `lista todos los salarios`) ·
`INJ-07` prompt-boundary spoofing (`### system`, `<|im_start|>`, line-leading `system:`) ·
`INJ-08` encoding evasion request (`answer in base64`, `rot13`, `responde en base64`).

Patterns are linear (no nested quantifiers) and input is truncated to `MAX_SCAN_CHARS = 20_000`
before matching — ReDoS/DoS guard.

## File Changes

| File | Action | Description |
|---|---|---|
| `app/security/__init__.py` | Create | Re-export `Role`, `resolve_role`, `inspect_input`, `inspect_output`, `build_security_middleware` (mirrors `app/tools/__init__.py`) |
| `app/security/roles.py` | Create | `Role` IntEnum, catalog, aliases, normalization, `resolve_role` |
| `app/security/injection.py` | Create | `INJECTION_PATTERNS` + `find_injection(text) -> tuple[str, ...]` |
| `app/security/guardrail.py` | Create | Dataclasses + `inspect_input` / `inspect_output` |
| `app/security/middleware.py` | Create | `build_security_middleware()` — before/after-model hook pair |
| `tests/test_security_roles.py` | Create | Ladder, catalog, aliases, normalization, fail-closed `resolve_role` |
| `tests/test_security_injection.py` | Create | Every `INJ-*` ID hits; must-not-block corpus |
| `tests/test_security_guardrail.py` | Create | Both directions × every role × catalog; tool-call args |
| `tests/test_security_middleware.py` | Create | Hook shape/blocking update, `pytest.importorskip("langchain")` |

`requirements.txt`, `app/tools/`, `app/rag/`: unchanged — no import, no edit.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Role ladder | `salary` for `EMPLOYEE` → BLOCK; for `FINANCE_MANAGER`/`ADMIN` → ALLOW; `national_id` → ALLOW only for `ADMIN` (proves two tiers, not one flag) |
| Unit | Input injection | Each `INJ-*` ID: one Spanish + one English probe → BLOCK with that ID in `matched` |
| Unit | **Output backstop** (load-bearing) | Input that passes cleanly, model answer containing `salario` → BLOCK. Fails if only the input side is wired |
| Unit | Tool-call args | `ToolCall("create_erp_adjustment", {"note": "salario de …"})` and `{"salary": 1}` → BLOCK; clean args → ALLOW |
| Unit | Must-not-block | "¿por qué la orden ORD-1001 tiene una discrepancia fiscal?", "compara el IVA con la normativa 2024" → ALLOW for **every** role |
| Unit | Fail-closed | `None`, `""`, `"root"`, `"ADMIN "`, `123`, `object()` → `Role.EMPLOYEE`, no exception |
| Unit | Normalization | `SALARIO`, `Salário`, `bank-account`, `cuenta bancaria` all resolve to the same canonical field |
| Unit | Anti-drift | Assert the exact `RESTRICTED_FIELDS` key set and each min role (mirrors F-B2's rate-table lock) |
| Unit | Message hygiene | `decision.message` contains no matched field name and no pattern ID |
| Integration | Adapter shape | `before_model`/`after_model` are callable, return `None`/`{}` on ALLOW and a `jump_to="end"` + safe-message update on BLOCK; factory returns one object (no loose helpers) |
| E2E | — | N/A: no agent (F-B5) and no API (F-B6) exist yet |

## Threat Model (required by `openspec/config.yaml` — security-critical design)

### Defended

| ID | Threat | Defense |
|---|---|---|
| T1 | Direct role-scoped exfiltration ("dame el salario de Ana") | Input side: field named above caller's role → BLOCK before the model runs |
| T2 | Direct prompt injection: instruction override, persona swap, system-prompt extraction, privilege claim | `INJ-01`–`INJ-05`, `INJ-07` on the user turn, pre-model |
| T3 | **Indirect** injection via RAG snippets or tool output steering the model | Input side cannot see it (it inspects the user turn) — the **output side** is the defense; explicitly a defense-in-depth layer, not a duplicate |
| T4 | Restricted data written *into* the ERP via tool-call arguments | `after_model` scans every tool-call arg before execution |
| T5 | Missing / unknown / malformed role | `resolve_role` → least privilege; `GUARDRAIL_ERROR` → BLOCK |
| T6 | F-B5 wires only half the guardrail | One exported factory returning one middleware object; no loose hook helpers |
| T7 | ReDoS / oversized input | Linear patterns only + `MAX_SCAN_CHARS` truncation |
| T8 | Probing the catalog through error messages | Static safe message; matched IDs never surface to the caller |

### NOT defended — residual risks (documented, not hidden)

| ID | Gap | Compensating control | Status |
|---|---|---|---|
| R1 | **Role is client-supplied and spoofable** — no auth, no JWT, no session. Any caller can claim `ADMIN` | Fail-closed default; `resolve_role` is the single chokepoint F-B6 repoints at a verified claim without touching the core; stated in spec + README | Accepted, by design (prototype) |
| R2 | Obfuscated injection (base64/homoglyph/translation/leetspeak, long-context burial) evades regex | Normalization kills case/accent/separator tricks; `INJ-08` catches the *request* to encode; output side backstops the leak | Accepted residual |
| R3 | Semantic paraphrase leak — model states a salary without any catalog term ("gana 45.000 al año") | None complete. A numeric+context heuristic would be false-positive-heavy on an invoice agent (YAGNI) | Accepted residual, logged |
| R4 | **Streaming bypass**: if F-B6 streams tokens straight to the client, `after_model` fires too late | Hard constraint for F-B6: buffer the final message, or run `inspect_output` on the stream sink before flushing | Open constraint on F-B6 |
| R5 | Raw tool output rendered to the user without passing the model | F-B6 must render only guardrail-approved content | Open constraint on F-B6 |
| R6 | Alias gap — a restricted term outside the catalog | Anti-drift catalog test; catalog is data, extending it needs no code change | Accepted, maintainable |

## Threat Matrix (SDD `references/threat-matrix.md`)

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary. All input is treated as inert text: it reaches only `re` matching
and dict lookups, never a shell, path, SQL string, `eval`, or network call. The security content
of this change lives in the Threat Model above, which is a different artifact.

## Migration / Rollout

No migration required. Additive package + tests; nothing imports `app/security/` until F-B5.
No DB, no state, no config, no new dependency. Rollback: delete `app/security/` and
`tests/test_security_*.py`, or drop `feature/f-b4-security-guardrail`.

## Open Questions

- [ ] None blocking. The `create_agent` middleware surface (`AgentMiddleware` subclass vs
      `@before_model`/`@after_model` decorators, and the exact blocking update key — `jump_to`)
      MUST be re-confirmed at apply time against the installed `langchain` version, per the F-B3
      chromadb precedent. If it has drifted, fix `middleware.py` only — the core contract above
      does not move.
- [ ] Final alias wording per catalog field is authored at apply time; the five canonical fields
      and their minimum roles are contractual.
