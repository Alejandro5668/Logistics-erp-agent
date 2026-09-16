"""Prompt-injection pattern detection (threats T2/T7, design.md).

Explicit, ID-tagged, compiled regex list — no ML classifier, no NLP
library, no external API (design.md Decision 4: a prototype guardrail must
be auditable, offline, deterministic, and fast). Each `INJ-*` ID has one
English and one Spanish variant covering the same attack shape:
instruction override, persona/role override, system-prompt extraction,
control disable, privilege claim, bulk exfiltration, prompt-boundary
spoofing, and encoding-evasion requests.

`MAX_SCAN_CHARS` truncates input before matching — patterns are linear (no
nested quantifiers) but truncation is a cheap, explicit ReDoS/DoS guard
regardless (threat T7).
"""

from __future__ import annotations

import re
import unicodedata

MAX_SCAN_CHARS = 20_000

# (pattern ID, regex). Two entries share an ID (one EN, one ES variant) for
# eight distinct IDs. Matched against normalized text (casefolded, accents
# stripped) — see `_normalize_for_scan` — so the patterns below don't need
# to spell out case/accent alternatives themselves.
INJECTION_PATTERNS: list[tuple[str, str]] = [
    # INJ-01 instruction override
    ("INJ-01", r"\bignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+instructions\b"),
    ("INJ-01", r"\b(ignora|olvida)\s+(todas\s+)?(las\s+)?instrucciones(\s+(anteriores|previas))?\b"),
    # INJ-02 persona / role override
    ("INJ-02", r"\byou are now\b"),
    ("INJ-02", r"\bact(?:u|ú)a\s+como\s+(?:el\s+|la\s+)?(?:administrador|admin)\b"),
    # INJ-03 system-prompt extraction
    ("INJ-03", r"\b(reveal|show|print|display)\s+(me\s+)?your\s+system\s+prompt\b"),
    ("INJ-03", r"\bmuestra(?:me)?\s+tu\s+prompt\b"),
    # INJ-04 control disable
    ("INJ-04", r"\b(disable|turn off|bypass)\s+(the\s+)?(guardrail|filter|security|safety)\b"),
    ("INJ-04", r"\bsin\s+restricciones\b"),
    # INJ-05 privilege claim
    ("INJ-05", r"\bi am (?:an |the )?admin(?:istrator)?\b"),
    ("INJ-05", r"\bsoy\s+(?:el\s+)?administrador\b"),
    # INJ-06 bulk exfiltration
    ("INJ-06", r"\bdump\s+all\s+(?:the\s+)?(?:fields|records|data)\b"),
    ("INJ-06", r"\blista\s+todos\s+los\s+salarios\b"),
    # INJ-07 prompt-boundary spoofing
    ("INJ-07", r"(###\s*system\b)|(<\|im_start\|>)"),
    ("INJ-07", r"^\s*sistema\s*:"),
    # INJ-08 encoding-evasion request
    ("INJ-08", r"\b(answer|respond)\s+in\s+(base64|rot13)\b"),
    ("INJ-08", r"\bresponde\s+en\s+base64\b"),
]

_COMPILED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (pattern_id, re.compile(pattern, re.IGNORECASE | re.MULTILINE))
    for pattern_id, pattern in INJECTION_PATTERNS
)


def _normalize_for_scan(text: str) -> str:
    """Casefold + strip accents (NFKD), keep whitespace/punctuation intact.

    Kills casing and accent evasion (`IGNORA` / `ignora` / `ígnora`) without
    collapsing structure the patterns rely on (line breaks for
    `INJ-07`'s line-leading anchor, literal `###`/`<|im_start|>` markup).
    """
    folded = (text or "").casefold()
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def find_injection(text: str) -> tuple[str, ...]:
    """Return every distinct `INJ-*` ID whose pattern matches `text`.

    Never raises: non-string input is coerced to `""`. Input is truncated
    to `MAX_SCAN_CHARS` before matching (ReDoS/DoS guard, threat T7).
    Result is deduplicated, in pattern-list order; empty tuple = clean.
    """
    try:
        safe_text = text if isinstance(text, str) else str(text or "")
    except Exception:
        return ()

    truncated = safe_text[:MAX_SCAN_CHARS]
    normalized = _normalize_for_scan(truncated)

    matched_ids: list[str] = []
    for pattern_id, compiled in _COMPILED_PATTERNS:
        if pattern_id in matched_ids:
            continue
        if compiled.search(normalized):
            matched_ids.append(pattern_id)
    return tuple(matched_ids)
