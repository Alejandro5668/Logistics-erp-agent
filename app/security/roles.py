"""Role ladder, restricted-field catalog, and fail-closed role resolution.

`Role` is a monotonic `IntEnum` ladder (`EMPLOYEE < FINANCE_MANAGER < ADMIN`)
so "does this caller outrank the field's minimum role" is one comparison
(`RESTRICTED_FIELDS[field] > role`), not a per-role branch (see design.md
Decision 2). `RESTRICTED_FIELDS` is the single source of truth for which
field names are protected and at what minimum role; `FIELD_ALIASES` maps
human phrasings (English/Spanish, including common misspellings/spacing) to
one of the five canonical keys, so the verdict rule exists exactly once
(DRY, design.md Decision 3).

Nothing here ever raises: `resolve_role()` is the fail-closed chokepoint —
absent, unknown, or malformed input always resolves to `Role.EMPLOYEE`
(least privilege), never to a privileged role and never an exception.
"""

from __future__ import annotations

import re
import unicodedata
from enum import IntEnum


class Role(IntEnum):
    """Visibility ladder. Higher value = more restricted fields visible."""

    EMPLOYEE = 1
    FINANCE_MANAGER = 2
    ADMIN = 3


# Canonical restricted field -> minimum role required to see it.
# This is the contractual catalog (design.md Interfaces / Contracts):
# exactly these five keys, exactly these minimum roles. Extending coverage
# is a data edit here, never a new code branch (OCP).
RESTRICTED_FIELDS: dict[str, Role] = {
    "salary": Role.FINANCE_MANAGER,
    "bank_account": Role.FINANCE_MANAGER,
    "employee_id": Role.FINANCE_MANAGER,
    "national_id": Role.ADMIN,
    "personal_contact": Role.ADMIN,
}

# Human phrasing (English/Spanish) -> canonical field. Keys are matched after
# normalization (see `_normalize_field`), so casing/accents/separators in
# this table are for readability only, not for matching correctness.
FIELD_ALIASES: dict[str, str] = {
    # salary / compensation
    "salary": "salary",
    "salario": "salary",
    "sueldo": "salary",
    "nomina": "salary",
    "nómina": "salary",
    "payroll": "salary",
    "compensation": "salary",
    "compensacion": "salary",
    "compensación": "salary",
    "bonus": "salary",
    # bank_account
    "bank_account": "bank_account",
    "bank account": "bank_account",
    "cuenta bancaria": "bank_account",
    "cuenta_bancaria": "bank_account",
    "iban": "bank_account",
    "account number": "bank_account",
    "numero de cuenta": "bank_account",
    "número de cuenta": "bank_account",
    # employee_id
    "employee_id": "employee_id",
    "employee id": "employee_id",
    "employee number": "employee_id",
    "legajo": "employee_id",
    # national_id
    "national_id": "national_id",
    "national id": "national_id",
    "ssn": "national_id",
    "dni": "national_id",
    "nif": "national_id",
    "tax id": "national_id",
    # personal_contact
    "personal_contact": "personal_contact",
    "personal contact": "personal_contact",
    "home address": "personal_contact",
    "personal email": "personal_contact",
    "telefono": "personal_contact",
    "teléfono": "personal_contact",
    "domicilio personal": "personal_contact",
}


def _normalize_field(text: str) -> str:
    """Normalize a phrase for alias/field matching.

    Pipeline (design.md Decision 8): casefold -> strip accents (NFKD) ->
    replace `_`/`-` with space -> collapse whitespace. Kills trivial casing,
    accent, and separator evasion (`SALARIO`, `Salário`, `bank-account`,
    `bank_account` all collapse to the same normalized form).
    """
    folded = (text or "").casefold()
    decomposed = unicodedata.normalize("NFKD", folded)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    separators_as_space = without_accents.replace("_", " ").replace("-", " ")
    return " ".join(separators_as_space.split())


# Built once at import time: normalized alias -> canonical field. Also seeds
# each canonical field's own normalized form, so a literal canonical key
# (e.g. "salary") always resolves even if omitted from FIELD_ALIASES.
_NORMALIZED_FIELD_LOOKUP: dict[str, str] = {}
for _alias, _canonical in FIELD_ALIASES.items():
    _NORMALIZED_FIELD_LOOKUP[_normalize_field(_alias)] = _canonical
for _canonical_field in RESTRICTED_FIELDS:
    _NORMALIZED_FIELD_LOOKUP.setdefault(_normalize_field(_canonical_field), _canonical_field)

# Longest alias first so a multi-word alias (e.g. "cuenta bancaria") is
# tried before a shorter one that might be its substring, and so the
# compiled word-boundary patterns below are deterministic to build once.
_COMPILED_FIELD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (canonical, re.compile(r"\b" + re.escape(normalized) + r"\b"))
    for normalized, canonical in sorted(
        _NORMALIZED_FIELD_LOOKUP.items(), key=lambda item: len(item[0]), reverse=True
    )
)


def find_restricted_fields(text: str) -> tuple[str, ...]:
    """Return every canonical restricted field named in `text`.

    Pure catalog lookup — no role comparison here (that is the guardrail's
    job). Matching is normalized (see `_normalize_field`) and
    word-boundary-aware so short aliases like "dni" or "nif" don't match
    inside unrelated words. Never raises: non-string input is coerced to
    `""`. Result is deduplicated and sorted for determinism.
    """
    try:
        normalized_text = _normalize_field(text if isinstance(text, str) else str(text or ""))
    except Exception:
        return ()

    matched: set[str] = set()
    for canonical, pattern in _COMPILED_FIELD_PATTERNS:
        if pattern.search(normalized_text):
            matched.add(canonical)
    return tuple(sorted(matched))


def resolve_role(raw: object) -> Role:
    """Resolve any caller-supplied value to a `Role`. Never raises.

    Fail-closed (design.md Decision 9 / spec "Fail-Closed Default"):
    `None`, empty string, unrecognized string, wrong type, or any other
    malformed input resolves to `Role.EMPLOYEE` (least privilege) — never to
    a privileged role, and never an exception.
    """
    if isinstance(raw, Role):
        return raw

    try:
        if isinstance(raw, str):
            candidate = raw.strip().upper()
            if candidate in Role.__members__:
                return Role[candidate]
            return Role.EMPLOYEE

        if isinstance(raw, bool):
            # bool is an int subclass; explicitly exclude it from the
            # int/IntEnum coercion path below so `True`/`False` fail closed
            # instead of silently resolving to EMPLOYEE/FINANCE_MANAGER.
            return Role.EMPLOYEE

        if isinstance(raw, int):
            return Role(raw)
    except (KeyError, ValueError):
        return Role.EMPLOYEE
    except Exception:
        return Role.EMPLOYEE

    return Role.EMPLOYEE
