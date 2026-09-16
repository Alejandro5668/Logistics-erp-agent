# Agent Core Specification

## Purpose

The single integration point wiring F-B1 (`get_erp_data`), F-B2
(`calculate_tax_discrepancy`), F-B3 (`search_regulations`), F-B4
(`build_security_middleware`), and two new mocked action tools into one
`create_agent` ReAct instance with thread-scoped session memory.

## Requirements

### Requirement: Agent Factory Interface

The system MUST expose `build_agent(model=None, checkpointer=None)`
returning a `create_agent` instance bound to exactly 5 tools
(`get_erp_data`, `calculate_tax_discrepancy`, `search_regulations`,
`create_erp_adjustment`, `notify_human`), with
`middleware=[build_security_middleware()]` wired, and a checkpointer wired
(`InMemorySaver` keyed by `thread_id` alone, when omitted).

#### Scenario: Default construction wires tools, middleware, and checkpointer

- GIVEN `build_agent()` is called with no arguments
- WHEN the returned agent is inspected
- THEN it exposes the 5 named tools, the security middleware, and a checkpointer keyed by `thread_id`

### Requirement: Model-Agnostic Model Parameter

`model` MUST accept either a provider-prefixed string (e.g.
`"azure_openai:gpt-4o"`) or a pre-built `BaseChatModel` instance. The
system MUST NOT hardcode one provider in `app/agent/core.py`.

#### Scenario: A fake/stub chat model instance is accepted

- GIVEN a test-only scripted `BaseChatModel` double
- WHEN `build_agent(model=fake_model)` is called
- THEN the agent runs using the injected fake model, with no network call

### Requirement: Action Tools in `app/tools/actions.py`

`app/tools/actions.py` MUST expose `create_erp_adjustment(order_id,
adjustment_amount, reason)` and `notify_human(order_id, reason)`, both
`@tool`-decorated, returning flat JSON dicts, never raising.
`create_erp_adjustment` MUST NOT write to `erp_orders`; it returns a
simulated receipt only. `notify_human` simulates a notification with no
real transport.

Param name clarification: `adjustment_amount = expected_tax - reported_tax`
(the correction to apply), distinct from `delta_pct` (F-B2's observed
percentage deviation) — the two names are kept separate on purpose so the
model cannot conflate the observed deviation with the correction.

#### Scenario: Adjustment returns a receipt without mutating the ERP table

- GIVEN a valid `order_id`, `adjustment_amount`, and free-text `reason`
- WHEN `create_erp_adjustment` is called
- THEN it returns a dict receipt with `order_id`, `adjustment_amount`, a status field
- AND the seeded `erp_orders` row for that `order_id` is unchanged

#### Scenario: Escalation call returns a deterministic record, never raising

- GIVEN a valid `order_id` and free-text `reason`
- WHEN `notify_human` is called
- THEN it returns a dict with `order_id`, `reason`, a status field, raising no exception regardless of `reason` content

### Requirement: Auto-Adjust Decision Policy

The system prompt MUST instruct the agent (never a hardcoded branch) to
call `create_erp_adjustment`, not `notify_human`, when
`calculate_tax_discrepancy`'s `delta_pct` is within ±5% AND
`search_regulations` returned ≥1 result for the relevant year.

#### Scenario: Small delta with regulatory backing auto-adjusts

- GIVEN `delta_pct` within ±5% and `search_regulations` returned ≥1 result for the queried year
- WHEN the agent completes its reasoning for that turn
- THEN `create_erp_adjustment` is called exactly once and `notify_human` is not called

### Requirement: Escalation Decision Policy

The system prompt MUST instruct the agent to call `notify_human`, not
`create_erp_adjustment`, whenever `delta_pct` is outside ±5% OR
`search_regulations` returned an empty result for the queried year — an
explicit escalation trigger, never silently ignored.

#### Scenario: Large delta escalates regardless of RAG result

- GIVEN `delta_pct` is outside ±5%
- WHEN the agent completes its reasoning for that turn
- THEN `notify_human` is called and `create_erp_adjustment` is not called

#### Scenario: Empty RAG result escalates even with a small delta

- GIVEN `delta_pct` within ±5% but `search_regulations` returned an empty list for the queried year
- WHEN the agent completes its reasoning for that turn
- THEN `notify_human` is called and `create_erp_adjustment` is not called

### Requirement: Guardrail Block Ends the Run With No Side-Effect Action

When F-B4's middleware blocks a turn on either the input or output side,
the run MUST end with F-B4's safe message and MUST NOT trigger
`create_erp_adjustment` or `notify_human` as a side effect of the block.

#### Scenario: Blocked turn fires no action tool

- GIVEN either `inspect_input` blocks the incoming turn or `inspect_output` blocks a mid-loop proposed tool call
- WHEN the run ends on that block
- THEN the run returns the safe message and neither action tool is called

### Requirement: Thread-Scoped Session Memory

The checkpointer MUST key state by `thread_id` alone. `role` MUST continue
to be supplied per-invocation (per F-B4's contract), never bound into the
thread/session.

#### Scenario: Second turn reuses resolved tool results

- GIVEN a first turn on `thread_id="t1"` already resolved `get_erp_data` and `calculate_tax_discrepancy` for an order
- WHEN a follow-up question on the same `thread_id="t1"` asks about the same order
- THEN the agent answers from checkpointed state without re-invoking either tool

### Requirement: Offline Test Seam Proves Wiring, Not Reasoning Quality

A project-owned scripted/fake chat model MUST exercise tool routing,
guardrail interception, and the decision policy with no network call or
credentials. This proves wiring correctness only; it MUST NOT be
represented as validating live-LLM reasoning quality.

#### Scenario: Fake-model test suite runs fully offline

- GIVEN a scripted fake model configured to emit a fixed tool-call sequence
- WHEN the test suite runs with no `AGENT_MODEL` credentials set
- THEN all wiring assertions pass with zero outbound network calls
