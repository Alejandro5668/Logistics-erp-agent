"""Synthetic normative corpus for the regulatory RAG pipeline.

Ships ~10 short Spanish normative snippets covering the cases F-B5's agent
needs to justify a tax-discrepancy decision: a discrepancy-tolerance rule,
regional VAT/IVA rates, and an adjustment-approval procedure. The snippets
are deliberately grouped into same-topic / different-year conflicts (e.g.
the tolerance percentage changes every year) so a year-metadata filter is
provably load-bearing rather than decorative — an unfiltered query for
"tolerancia" must return a mix of years, and a filtered one must not.

Distribution: 3 x 2022, 3 x 2023, 4 x 2024 (10 total).
"""

from __future__ import annotations

# fmt: off
REGULATION_SNIPPETS = [
    # --- Tolerancia de discrepancia fiscal (same topic, 3 years, 3 rules) ---
    {
        "doc_id": "REG-2022-001",
        "title": "Tolerancia de discrepancia fiscal (2022)",
        "year": 2022,
        "source": "Reglamento Fiscal 2022, Art. 14",
        "text": (
            "Durante el ejercicio 2022, se admite una tolerancia de discrepancia "
            "fiscal del 5% o 50 EUR (lo que sea mayor) entre el importe facturado "
            "y el importe calculado por el sistema, sin necesidad de ajuste manual."
        ),
    },
    {
        "doc_id": "REG-2023-001",
        "title": "Tolerancia de discrepancia fiscal (2023)",
        "year": 2023,
        "source": "Reglamento Fiscal 2023, Art. 14",
        "text": (
            "Durante el ejercicio 2023, la tolerancia de discrepancia fiscal se "
            "reduce al 2% o 25 EUR (lo que sea mayor) entre el importe facturado y "
            "el importe calculado por el sistema, sin necesidad de ajuste manual."
        ),
    },
    {
        "doc_id": "REG-2024-001",
        "title": "Tolerancia de discrepancia fiscal (2024)",
        "year": 2024,
        "source": "Reglamento Fiscal 2024, Art. 14",
        "text": (
            "Durante el ejercicio 2024, la tolerancia de discrepancia fiscal se "
            "reduce al 1% o 10 EUR (lo que sea mayor) entre el importe facturado y "
            "el importe calculado por el sistema, sin necesidad de ajuste manual."
        ),
    },
    # --- Tipo impositivo EU-ES (2022 vs 2024, 2023 has no update) ---
    {
        "doc_id": "REG-2022-002",
        "title": "Tipo impositivo EU-ES (2022)",
        "year": 2022,
        "source": "Reglamento Fiscal 2022, Art. 7",
        "text": (
            "Para la región EU-ES, el tipo impositivo aplicable en 2022 es del 21% "
            "(IVA general), sin requisito documental adicional para su aplicación."
        ),
    },
    {
        "doc_id": "REG-2024-002",
        "title": "Tipo impositivo EU-ES (2024)",
        "year": 2024,
        "source": "Reglamento Fiscal 2024, Art. 7",
        "text": (
            "Para la región EU-ES, el tipo impositivo aplicable en 2024 sigue "
            "siendo del 21% (IVA general), pero ahora requiere justificación "
            "documental adjunta a la factura para su aplicación."
        ),
    },
    # --- Tipos regionales EU-DE / LATAM-CO (2023 only, plus 2024 update) ---
    {
        "doc_id": "REG-2023-002",
        "title": "Tipo impositivo EU-DE (2023)",
        "year": 2023,
        "source": "Reglamento Fiscal 2023, Art. 8",
        "text": (
            "Para la región EU-DE, el tipo impositivo aplicable en 2023 es del 19% "
            "(IVA general alemán)."
        ),
    },
    {
        "doc_id": "REG-2023-003",
        "title": "Tipo impositivo LATAM-CO (2023)",
        "year": 2023,
        "source": "Reglamento Fiscal 2023, Art. 9",
        "text": (
            "Para la región LATAM-CO, el tipo impositivo aplicable en 2023 es del "
            "19% (IVA general colombiano)."
        ),
    },
    {
        "doc_id": "REG-2024-003",
        "title": "Tipo impositivo LATAM-CO (2024)",
        "year": 2024,
        "source": "Reglamento Fiscal 2024, Art. 9",
        "text": (
            "Para la región LATAM-CO, el tipo impositivo aplicable en 2024 sigue "
            "siendo del 19%, pero se añade una retención en la fuente adicional "
            "sobre el importe neto de la factura."
        ),
    },
    # --- Procedimiento de ajuste (2022 vs 2024) ---
    {
        "doc_id": "REG-2022-003",
        "title": "Procedimiento de ajuste automático (2022)",
        "year": 2022,
        "source": "Reglamento Fiscal 2022, Art. 21",
        "text": (
            "En 2022, el ajuste automático de discrepancias fiscales está permitido "
            "para importes iguales o inferiores a 100 EUR, sin intervención humana."
        ),
    },
    {
        "doc_id": "REG-2024-004",
        "title": "Procedimiento de ajuste automático (2024)",
        "year": 2024,
        "source": "Reglamento Fiscal 2024, Art. 21",
        "text": (
            "Desde 2024, el ajuste automático de discrepancias fiscales queda "
            "prohibido en todos los casos; toda discrepancia requiere aprobación "
            "humana explícita antes de aplicarse."
        ),
    },
]
# fmt: on


def ingest_corpus(collection) -> None:
    """Upsert REGULATION_SNIPPETS into the given Chroma collection, idempotently.

    Uses `collection.upsert()` (upsert-by-id, the Chroma equivalent of F-B1's
    `session.merge()`), so re-running this function against an already-seeded
    collection is a no-op: no duplicate `doc_id` entries are created and
    existing entries are refreshed to match REGULATION_SNIPPETS.

    Receives the collection as a parameter (DIP) so this module has no
    dependency on `app.rag.store` and imports nothing.
    """
    collection.upsert(
        ids=[record["doc_id"] for record in REGULATION_SNIPPETS],
        documents=[record["text"] for record in REGULATION_SNIPPETS],
        metadatas=[
            {
                "title": record["title"],
                "year": record["year"],
                "source": record["source"],
            }
            for record in REGULATION_SNIPPETS
        ],
    )


if __name__ == "__main__":
    from app.rag.store import _get_collection

    seeded_collection = _get_collection()  # first access already upserts
    ingest_corpus(seeded_collection)  # explicit re-run stays a no-op (idempotent)
    print(f"Ingested {len(REGULATION_SNIPPETS)} regulation snippet(s).")
    print(f"Collection count: {seeded_collection.count()}")
