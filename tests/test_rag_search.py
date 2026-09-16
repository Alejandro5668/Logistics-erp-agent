"""Tests for app.rag.store / app.rag.corpus.

Covers the spec's acceptance criteria: correct-year hit, cross-year
exclusion (the load-bearing test proving `where=` is not decorative), empty
result behavior, flat JSON-safe shape, ingestion idempotency, and LangChain
bindability. All tests run against an isolated tmp_path Chroma store with a
deterministic offline embedding function via the `regulations_index`
fixture in conftest.py — no network access, no ONNX model.

Query wording deliberately reuses the corpus's own vocabulary (e.g.
"tolerancia de discrepancia fiscal", matching REG-*-001's exact wording)
rather than paraphrasing it: the deterministic stub embedding is an exact
hashed bag-of-words with no stemming, so exact lexical overlap is what
drives ranking — this is what makes the fixture-authored cross-year
conflicts provably exercise the `where` filter instead of relying on a real
semantic model.
"""

import json

from app.rag import search_regulations
from app.rag.corpus import REGULATION_SNIPPETS, ingest_corpus
from app.rag.store import _get_collection

TOLERANCE_QUERY = "tolerancia de discrepancia fiscal"


class TestSearchRegulationsCorrectYearHit:
    def test_default_year_returns_2024_tolerance_snippet(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY})

        doc_ids = [row["doc_id"] for row in result]
        assert "REG-2024-001" in doc_ids

        hit = next(row for row in result if row["doc_id"] == "REG-2024-001")
        assert hit["year"] == 2024
        assert "1%" in hit["text"]


class TestSearchRegulationsCrossYearExclusion:
    def test_year_2024_excludes_every_other_year(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY, "year": 2024})

        assert len(result) > 0
        assert all(row["year"] == 2024 for row in result)

    def test_year_2022_returns_only_2022_tolerance_snippet(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY, "year": 2022})

        doc_ids = [row["doc_id"] for row in result]
        assert "REG-2022-001" in doc_ids
        assert all(row["year"] == 2022 for row in result)

        hit = next(row for row in result if row["doc_id"] == "REG-2022-001")
        assert "5%" in hit["text"]

    def test_year_2023_returns_only_2023_tolerance_snippet(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY, "year": 2023})

        doc_ids = [row["doc_id"] for row in result]
        assert "REG-2023-001" in doc_ids
        assert all(row["year"] == 2023 for row in result)

        hit = next(row for row in result if row["doc_id"] == "REG-2023-001")
        assert "2%" in hit["text"]


class TestFilterIsNotDecorative:
    """The load-bearing test: fails if `where=` is ever removed from the tool."""

    def test_unfiltered_query_spans_more_than_one_year(self, regulations_index):
        # Query the raw collection directly, bypassing the tool entirely, and
        # WITHOUT a `where` clause.
        raw_result = regulations_index.query(
            query_texts=[TOLERANCE_QUERY],
            n_results=3,
        )
        years = {metadata["year"] for metadata in raw_result["metadatas"][0]}

        assert len(years) > 1

    def test_tool_filtered_result_spans_exactly_one_year(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY, "year": 2024})
        years = {row["year"] for row in result}

        assert years == {2024}


class TestSearchRegulationsEmptyResult:
    def test_unmatched_year_returns_empty_list_without_raising(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY, "year": 1999})

        assert isinstance(result, list)
        assert result == []

    def test_empty_query_string_does_not_raise(self, regulations_index):
        result = search_regulations.invoke({"query": "", "year": 2024})

        assert isinstance(result, list)


class TestSearchRegulationsFlatShape:
    def test_result_rows_have_exact_keys_and_scalar_values(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY, "year": 2024})

        assert len(result) > 0
        for row in result:
            assert set(row.keys()) == {"doc_id", "title", "year", "source", "text", "score"}
            for value in row.values():
                assert isinstance(value, (str, int, float, bool)) or value is None

    def test_result_is_json_serializable(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY, "year": 2024})

        assert json.dumps(result)

    def test_result_is_capped_at_three(self, regulations_index):
        # year=2024 has 4 seeded snippets; the result must still be capped.
        result = search_regulations.invoke({"query": "impositivo", "year": 2024})

        assert len(result) <= 3


class TestIngestionIdempotency:
    def test_running_ingest_corpus_twice_keeps_count_stable(self, regulations_index):
        ingest_corpus(regulations_index)
        ingest_corpus(regulations_index)

        assert regulations_index.count() == len(REGULATION_SNIPPETS)

    def test_running_ingest_corpus_twice_keeps_no_duplicate_doc_ids(self, regulations_index):
        ingest_corpus(regulations_index)
        ingest_corpus(regulations_index)

        stored = regulations_index.get()
        assert len(stored["ids"]) == len(set(stored["ids"]))


class TestSearchRegulationsToolBindability:
    def test_tool_exposes_name_and_args_schema(self, regulations_index):
        assert search_regulations.name
        assert search_regulations.args_schema is not None

    def test_tool_invoke_with_default_year_returns_list(self, regulations_index):
        result = search_regulations.invoke({"query": TOLERANCE_QUERY})

        assert isinstance(result, list)

    def test_get_collection_is_the_same_cached_instance_as_the_fixture(self, regulations_index):
        assert _get_collection() is regulations_index
