# Verification Report - f-b1-erp-mock

**Change**: F-B1 - Mock ERP Data Layer (`get_erp_data`)
**Branch**: `feature/f-b1-erp-mock`
**Mode**: Full spec-driven verification (proposal, specs, design, tasks all present)
**Date**: 2026-09-15

## Completeness Table

| Phase | Tasks | Status |
|---|---|---|
| 1. Foundation & Package Bootstrap | 1.1-1.4 | All 4 checked, verified present on disk |
| 2. ORM Model & Engine Layer | 2.1-2.4 | All 4 checked, verified in `app/tools/erp_data.py` |
| 3. Seed Module & Dataset | 3.1-3.4 | All 4 checked, verified in `app/tools/erp_seed.py` |
| 4. LangChain Tool Adapter | 4.1-4.4 | All 4 checked, verified in `app/tools/erp_data.py` |
| 5. Test Infrastructure | 5.1-5.3 | All 3 checked, verified in `tests/` |
| 6. Test Verification | 6.1-6.4 | All 4 checked, verified via passing `pytest -v` run |

23/23 tasks checked in `tasks.md`; all files listed in "File Changes" (design.md) and "Suggested Work Units" (tasks.md) exist and are git-tracked: `app/__init__.py`, `app/tools/__init__.py`, `app/tools/erp_data.py`, `app/tools/erp_seed.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_erp_data.py`, `requirements.txt`, `.gitignore`.

## Build/Test Evidence

Command: `python -m pytest -v` (repo root, branch `feature/f-b1-erp-mock`)

```
collected 19 items
... 19 passed in 0.54s
```

Exit code: 0. All 19 tests pass - no skips, no xfails, no warnings.

No separate build/type-check command is defined for this Python project; `requirements.txt` matches the design's declared dependency list (`sqlalchemy>=2.0`, `langchain-core>=0.1`, `pytest>=7.0`).

## Spec Compliance Matrix

| Requirement | Scenario | Covering Test(s) | Status |
|---|---|---|---|
| Tool Interface | Tool is bindable by the agent | TestGetErpDataToolBindability (.name, .args_schema, .invoke()) | PASS |
| Parametrized Query Execution | Clean matching lookup | test_returns_seeded_record_with_exact_field_values | PASS |
| Parametrized Query Execution | Quote/comment-bearing order_id is a literal, not code | test_or_1_equals_1_payload_returns_not_found, test_drop_table_comment_payload_returns_not_found, test_table_is_still_queryable_after_injection_attempts, test_injection_payload_never_returns_multiple_rows | PASS |
| Deterministic Not-Found Behavior | Unknown order_id | test_unknown_order_id_returns_not_found_without_raising | PASS |
| Deterministic Not-Found Behavior | Empty or whitespace order_id | test_empty_string_returns_not_found, test_whitespace_only_returns_not_found | PASS |
| Seeded Dataset Coverage | Tax mismatch / wrong-region records retrievable as-is | test_tax_mismatch_record_is_returned_unmodified, test_wrong_region_record_is_returned_unmodified | PASS |
| Seeded Dataset Coverage | Cancelled or pending record retrievable | test_cancelled_status_is_preserved, test_pending_status_is_preserved | PASS |
| Seeded Dataset Coverage | Re-running the seed script is idempotent | test_running_seed_database_twice_keeps_row_count_stable, test_running_seed_database_twice_keeps_data_matching_single_run | PASS |
| Flat Return Shape | Return shape is a flat dict | test_hit_result_has_exact_keys_and_scalar_values, test_hit_result_is_json_serializable, test_miss_result_is_json_serializable | PASS |

9/9 spec scenarios have a passing, runtime-verified covering test. No UNTESTED or FAILING scenarios.

## Correctness Checks (code inspection)

- `_fetch_order` uses `select(ErpOrder).where(ErpOrder.order_id == order_id)` - ORM-bound parameter by construction; no f-string/.format()/+ concatenation with order_id anywhere in erp_data.py or erp_seed.py. Confirmed by direct read of both files.
- `get_erp_data` never raises for missing/malformed input: empty/whitespace short-circuits to `_not_found` before any query; `_fetch_order` returning None also routes to `_not_found`. No bare except swallowing real errors - none needed, since the ORM path cannot throw on a literal-bound miss.
- Money handling: Numeric(12,2)/Decimal in the ORM model, float() conversion only at the `_to_flat_dict` tool boundary - matches design's stated rationale (decimal precision internally, JSON-safe externally).
- Return shape: hit dict has exactly found, order_id, net_amount, tax_amount, total_amount, region, status - matches design's documented contract and the spec's "at minimum" field list.
- .gitignore covers the data/*.db equivalent (*.db, data/) plus extra entries (.venv/, .env, chroma_db/) not required by this change but harmless.
- No data/ directory or .db file is tracked by git - confirmed via git ls-files and git status --ignored.

## Design Coherence

| Design Decision | Implementation | Match |
|---|---|---|
| ORM select() with Python-value where clause | _fetch_order | Yes |
| 2 layers in 1 file (erp_data.py) + separate seed module | Confirmed file layout | Yes |
| ERP_DB_PATH env var, default data/erp_mock.db, read at call time | _get_erp_db_path() reads os.environ inside _get_engine(), not at import | Yes |
| Module-level lazy _get_engine() cached after first call | _engine/_session_factory globals, lazy build | Yes |
| Numeric(12,2) + float() boundary conversion | Confirmed | Yes |
| Not-found dict shape (no exception, no None) | _not_found() | Yes |
| session.merge() upsert-by-PK over create_all() | seed_database() | Yes |

## Seed Dataset Note

Seed dataset contains 9 rows in SEED_ORDERS (ORD-1001 through ORD-1009) covering 3 clean matches, 2 tax mismatches, 2 wrong-region records, 1 cancelled, and 1 pending order, plus ORD-9999 intentionally absent as the documented missing-order case. Design.md's "Seed Dataset (10 records)" header refers to 10 conceptual coverage cases (9 seeded plus 1 deliberately-absent), not 10 DB rows, consistent with the design's own breakdown table and with tasks.md task 3.1's enumeration (which lists "1 deliberately missing, ORD-9999 doc only" as part of the same 10-item count). Not a deviation from spec, which only requires coverage of these categories "at minimum."

## Reported Deviations - Verified

1. `_reset_engine_cache()` test-only helper (not itemized in tasks.md)

Because the design intentionally caches the engine at module level (an explicit, justified decision for production use), a test suite that flips ERP_DB_PATH per test via monkeypatch needs a way to invalidate that cache, otherwise tests would silently reuse a stale engine bound to a previous test temp DB, or to the default data/erp_mock.db path. This is exactly the failure mode the design's own engine-lifetime rationale warns about (import-time engine freezes the env var before tests can set it). The helper is tests-facing only (prefixed underscore, docstring says "test-only escape hatch"), does not change any public contract, and is exercised implicitly by every test via the erp_db fixture. Verdict: sane, justified, no spec or design violation. WARNING level only (documentation gap), since it is not itemized as its own task but is implied by task 5.2 and 5.3's isolation requirement.

2. engine.dispose() in the erp_db fixture teardown (Windows file-lock cleanup)

SQLite on Windows keeps an OS-level file handle open via the engine's connection pool. Without disposing the engine first, the fixture's subsequent db_path.unlink() call can fail with a PermissionError on Windows because the file is still locked by the process. Disposing before unlinking is a standard SQLAlchemy pattern for exactly this problem and has no production-code impact since it lives entirely in tests/conftest.py. Verdict: sane, justified, no spec or design violation. WARNING level only (documentation gap), a reasonable test-infra addition not called out in tasks.md 5.2.

Both deviations are confined to test infrastructure, do not alter the documented tool contract, do not weaken any spec guarantee, and were necessary given the design's own module-level-caching decision. Neither is a CRITICAL finding.

## Issues

### CRITICAL

None.

### WARNING

- W1: _reset_engine_cache() exists in app/tools/erp_data.py but is not itemized in tasks.md (Phase 2 or 5). Recommend a one-line tasks.md addendum for traceability before archive, or accept as implied by 5.2/5.3.
- W2: engine.dispose() in tests/conftest.py's erp_db fixture teardown is not itemized in tasks.md 5.2. Recommend the same one-line addendum, or accept as implied by "fixture teardown cleans up the temp DB file."

### SUGGESTION

- S1: No test exercises a non-str malformed order_id (for example None or an int); only empty-string and whitespace-only are tested, which matches exactly what the spec's scenarios describe, so this is not a compliance gap, just a possible future hardening test if LangChain's own arg-schema coercion behavior ever changes.
- S2: Design's "Seed Dataset (10 records)" header is worded ambiguously against its own 9-seeded-row breakdown; consider clarifying to "10 dataset cases (9 seeded plus 1 documented absent)" in a future design revision to avoid future-reader confusion. No functional impact.

## Final Verdict

PASS WITH WARNINGS

All 23 tasks are complete and match the code on disk. All 9 spec scenarios across all 5 requirements have a passing, runtime-verified covering test (19 of 19 pytest -v green, exit code 0). No CRITICAL issues. Two WARNING-level documentation gaps (test-only helper and Windows-specific teardown call not itemized in tasks.md) are both technically justified by the design's own module-level engine-caching decision and by Windows SQLite file-locking behavior; neither weakens a spec guarantee. Safe to proceed to archive; the WARNINGs are optional tasks.md hygiene, not blockers.
