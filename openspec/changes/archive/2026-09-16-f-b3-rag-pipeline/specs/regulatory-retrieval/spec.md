# Regulatory Retrieval Specification

## Purpose

Provide a year-filtered semantic lookup over a local corpus of Spanish
normative snippets (tax-discrepancy tolerances and regional tax rules), so
an agent can justify a tax-discrepancy decision against the regulation in
force for a specific year rather than a superseded one. Exposed as a
LangChain-bindable tool the agent can call directly.

## Requirements

### Requirement: Tool Interface and Bindability

The system MUST expose a `search_regulations(query: str, year: int = 2024)`
function decorated as a LangChain `@tool`, bindable to an LLM/agent tool
list without additional adaptation.

#### Scenario: Tool is bindable with default year

- GIVEN the `search_regulations` tool is imported
- WHEN it is added to an agent's tool list and bound to an LLM
- THEN the binding MUST succeed without error
- AND the tool MUST be invocable with only a `query` argument, using
  `year=2024` as the default

#### Scenario: Tool accepts explicit year override

- GIVEN the `search_regulations` tool
- WHEN invoked with `query="tolerancia de discrepancia"` and `year=2023`
- THEN the tool MUST query the store filtered to `year=2023` and return a
  result, without raising

### Requirement: Metadata-Filter Correctness

The system MUST apply the `year` filter as an exact-match query-time filter
(`where={"year": year}`) against the vector store, and MUST NOT include any
chunk whose `year` metadata differs from the requested year, regardless of
topical similarity. The system MUST NOT fall back to a nearby or older year
when the requested year has no match.

#### Scenario: Only the requested year is returned

- GIVEN the corpus contains chunks for `year=2022`, `year=2023`, and
  `year=2024` on the same topic (discrepancy tolerance)
- WHEN `search_regulations("tolerancia de discrepancia", year=2024)` is
  called
- THEN every returned result MUST have `year == 2024`

#### Scenario: Same-topic different-year document is excluded

- GIVEN the corpus contains a 2022 chunk and a 2024 chunk that are both
  semantically close to the query text (same topic, different rule)
- WHEN `search_regulations(query, year=2024)` is called
- THEN the 2022 chunk MUST NOT appear anywhere in the returned results
- AND this MUST hold even though the 2022 chunk would rank as a top
  semantic match without the filter

### Requirement: Empty-Result Behavior

The system MUST return an empty result (empty list) when no chunk matches
the requested `year`, and MUST NOT raise an exception, MUST NOT fall back
to another year, and MUST NOT return unfiltered results.

#### Scenario: Year with no matching chunks

- GIVEN the corpus has no chunks with `year=2099`
- WHEN `search_regulations(query, year=2099)` is called
- THEN the call MUST return an empty list
- AND no exception MUST be raised

### Requirement: Idempotent Ingestion

The system MUST support re-running the ingestion/bootstrap process against
an existing persistent collection without creating duplicate chunks or
duplicate `doc_id` entries.

#### Scenario: Re-running ingestion twice

- GIVEN the corpus has already been ingested into the persistent collection
  at `CHROMA_DB_PATH`
- WHEN the ingestion process is run again unchanged
- THEN the collection's chunk count MUST remain the same as after the first
  run
- AND no `doc_id` MUST appear more than once in the collection

### Requirement: Flat Result Shape

The system MUST return results as a flat list of dicts, each containing
`doc_id`, `title`, `year`, `source`, `text`, and `score`, capped at
approximately 3 results per call, with no nested store-specific structures.

#### Scenario: Successful query returns capped flat dicts

- GIVEN a query that matches more than 3 chunks for the requested year
- WHEN `search_regulations(query, year=2024)` is called
- THEN the result MUST be a list of at most 3 dicts
- AND each dict MUST contain exactly the keys `doc_id`, `title`, `year`,
  `source`, `text`, `score`
