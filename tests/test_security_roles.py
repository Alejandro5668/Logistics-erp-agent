"""Tests for app.security.roles.

Covers the role ladder, the restricted-field catalog anti-drift lock
(mirrors F-B2's rate-table anti-drift test), alias resolution, the
normalization pipeline (casing/accent/separator evasion), and the
fail-closed guarantee of `resolve_role()` — it must never raise and must
never resolve unknown input to anything above `Role.EMPLOYEE`.

Pure functions, no fixtures, no I/O.
"""

import pytest

from app.security.roles import (
    FIELD_ALIASES,
    RESTRICTED_FIELDS,
    Role,
    find_restricted_fields,
    resolve_role,
)


class TestRoleLadder:
    def test_role_ordering_is_monotonic(self):
        assert Role.EMPLOYEE < Role.FINANCE_MANAGER < Role.ADMIN

    def test_salary_blocked_for_employee_allowed_for_finance_manager_and_admin(self):
        min_role = RESTRICTED_FIELDS["salary"]

        assert min_role > Role.EMPLOYEE
        assert not (min_role > Role.FINANCE_MANAGER)
        assert not (min_role > Role.ADMIN)


class TestRestrictedFieldsAntiDrift:
    """Locks the catalog's key set and each minimum role.

    Fails loudly if a field is added/removed/renamed or its minimum role
    changes without an explicit, reviewed edit here.
    """

    def test_exact_key_set(self):
        assert set(RESTRICTED_FIELDS.keys()) == {
            "salary",
            "bank_account",
            "employee_id",
            "national_id",
            "personal_contact",
        }

    def test_exact_minimum_roles(self):
        assert RESTRICTED_FIELDS["salary"] == Role.FINANCE_MANAGER
        assert RESTRICTED_FIELDS["bank_account"] == Role.FINANCE_MANAGER
        assert RESTRICTED_FIELDS["employee_id"] == Role.FINANCE_MANAGER
        assert RESTRICTED_FIELDS["national_id"] == Role.ADMIN
        assert RESTRICTED_FIELDS["personal_contact"] == Role.ADMIN


class TestFieldAliases:
    @pytest.mark.parametrize(
        ("alias", "canonical"),
        [
            ("salario", "salary"),
            ("sueldo", "salary"),
            ("nomina", "salary"),
            ("cuenta bancaria", "bank_account"),
            ("cuenta_bancaria", "bank_account"),
            ("iban", "bank_account"),
            ("legajo", "employee_id"),
            ("employee number", "employee_id"),
            ("dni", "national_id"),
            ("ssn", "national_id"),
            ("telefono", "personal_contact"),
            ("home address", "personal_contact"),
        ],
    )
    def test_alias_resolves_to_canonical_field(self, alias, canonical):
        assert FIELD_ALIASES[alias] == canonical
        assert find_restricted_fields(f"please share the {alias}") == (canonical,)


class TestNormalization:
    @pytest.mark.parametrize(
        "phrasing",
        ["SALARIO", "Salário", "salario", "  SaLaRiO  "],
    )
    def test_salary_variants_resolve_to_same_canonical_field(self, phrasing):
        assert find_restricted_fields(f"dame el {phrasing} de Juan") == ("salary",)

    def test_underscore_and_hyphen_separators_both_resolve(self):
        assert find_restricted_fields("bank-account details please") == ("bank_account",)
        assert find_restricted_fields("bank_account details please") == ("bank_account",)
        assert find_restricted_fields("bank account details please") == ("bank_account",)

    def test_short_alias_does_not_match_inside_unrelated_word(self):
        # "dni" (national_id alias) must not match when it's only a
        # substring of a longer, unrelated word — word-boundary-aware
        # matching, not a bare substring check.
        assert find_restricted_fields("this is about abdniba nonsense") == ()


class TestResolveRoleFailClosed:
    @pytest.mark.parametrize(
        "raw",
        [None, "", "root", "ADMIN ", 123, object(), 0, -1, 3.5, [], {}],
    )
    def test_unknown_or_malformed_resolves_to_employee_no_exception(self, raw):
        assert resolve_role(raw) == Role.EMPLOYEE

    def test_bool_does_not_coerce_via_int(self):
        # bool is an int subclass; True/False must NOT silently resolve to
        # FINANCE_MANAGER(2-ish)/EMPLOYEE(1-ish) via int coercion.
        assert resolve_role(True) == Role.EMPLOYEE
        assert resolve_role(False) == Role.EMPLOYEE

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("EMPLOYEE", Role.EMPLOYEE),
            ("employee", Role.EMPLOYEE),
            ("FINANCE_MANAGER", Role.FINANCE_MANAGER),
            ("ADMIN", Role.ADMIN),
            ("admin", Role.ADMIN),
            (Role.ADMIN, Role.ADMIN),
            (1, Role.EMPLOYEE),
            (2, Role.FINANCE_MANAGER),
            (3, Role.ADMIN),
        ],
    )
    def test_recognized_values_resolve_correctly(self, raw, expected):
        assert resolve_role(raw) == expected

    def test_never_raises_for_arbitrary_garbage(self):
        class Unpredictable:
            def __eq__(self, other):
                raise RuntimeError("should never be called by resolve_role")

            def __hash__(self):
                raise RuntimeError("should never be called by resolve_role")

        try:
            result = resolve_role(Unpredictable())
        except Exception as exc:  # pragma: no cover - defensive, must not trigger
            pytest.fail(f"resolve_role raised unexpectedly: {exc}")

        assert result == Role.EMPLOYEE


class TestFindRestrictedFields:
    def test_no_restricted_field_in_benign_text_returns_empty(self):
        assert find_restricted_fields("Why is order 123 off by $50?") == ()

    def test_multiple_fields_in_same_text_are_all_returned(self):
        result = find_restricted_fields("share the salario and the dni please")
        assert set(result) == {"salary", "national_id"}

    def test_non_string_input_never_raises(self):
        try:
            result = find_restricted_fields(None)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - defensive, must not trigger
            pytest.fail(f"find_restricted_fields raised unexpectedly: {exc}")

        assert result == ()
