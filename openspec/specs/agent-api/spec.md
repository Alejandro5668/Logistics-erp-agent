# Agent API Specification

## Purpose

Two-endpoint HTTP layer over F-B5's agent (SSE streaming and JSON non-streaming), sharing one guarded execution path so no content reaches a client unevaluated by F-B4's `inspect_output`.

## Requirements

### Requirement: Chat Endpoint Contracts

Both endpoints MUST accept `{message, thread_id, role}` and MUST invoke one shared guarded execution pipeline; the system MUST NOT maintain divergent guardrail logic per endpoint.

| Endpoint | Success | Malformed body |
|---|---|---|
| `POST /chat` (SSE) | `text/event-stream`: `progress`/`content` events, then one terminal event | HTTP 422, no stream opened |
| `POST /chat/sync` (JSON) | HTTP 200 `{content, thread_id, status}` | HTTP 422 |

#### Scenario: Streaming endpoint completes normally

- GIVEN a well-formed request
- WHEN `POST /chat` is called
- THEN events stream, ending in one terminal event

#### Scenario: Non-streaming endpoint completes normally

- GIVEN a well-formed request
- WHEN `POST /chat/sync` is called
- THEN it returns 200 with guardrail-approved `content`

### Requirement: No Unguarded Content Reaches the Client

The system MUST NOT transmit model text or tool output before `inspect_output` has evaluated the accumulated content covering it. If pre-flush token-level evaluation is unsound for the installed `langgraph`'s event granularity, the system MUST fall back to evaluate-then-flush chunked delivery instead of unguarded tokens. Tool arguments/results MUST NEVER appear in any event.

#### Scenario: Guarded content streams progressively

- GIVEN an allowed request
- WHEN the agent generates output
- THEN each `content` event covers only text already passed through `inspect_output`

#### Scenario: Guardrail blocks output mid-generation

- GIVEN output inspection fails partway through generation
- WHEN the block is detected
- THEN no un-inspected suffix is ever emitted as `content`

### Requirement: Progress Events During Tool Execution

The system MUST emit `progress` events carrying only a static label naming the running tool; progress events MUST NOT carry tool arguments or results.

#### Scenario: Tool call emits label-only progress

- GIVEN the agent invokes a tool
- WHEN execution starts
- THEN a `progress` event with only a name/status label is emitted

### Requirement: Blocked-Turn Replace Semantics

When the guardrail blocks input or output mid-stream, the system MUST emit exactly one terminal `blocked` event carrying the complete safe message, superseding any prior `content` events for that turn.

#### Scenario: Output blocked after partial content sent

- GIVEN some `content` events already sent
- WHEN output inspection then blocks
- THEN a terminal `blocked` event instructs discarding prior content

#### Scenario: Input blocked before generation

- GIVEN input inspection blocks the request
- WHEN the run begins
- THEN only the terminal `blocked` event is sent, no prior `content`

### Requirement: Role and Thread_id Propagation

The system MUST forward `role` as `context={"role": role}` (per `_role_from_context`) and `thread_id` to F-B5's checkpointer, identically on both endpoints.

#### Scenario: Role changes guardrail outcome

- GIVEN identical restricted-field requests with `role="EMPLOYEE"` vs `"ADMIN"`
- WHEN each is sent
- THEN EMPLOYEE is blocked and ADMIN succeeds

#### Scenario: Thread continuity across turns

- GIVEN two requests share the same `thread_id`
- WHEN the second is sent
- THEN the response reflects state from the first turn

### Requirement: Failure Handling and Checkpointer Safety

On provider failure (timeout, rate limit, auth, network) or an unexpected LangGraph graph/tool-node error (distinct from F-B1's never-raise tool contract), the system MUST return a generic client-safe error, never leaking provider details or stack traces, and MUST NOT leave checkpointer state for that `thread_id` corrupted or partial. Failures before the first byte MUST surface as an HTTP error status; failures after SSE headers are sent MUST surface as a terminal `error` event.

#### Scenario: Provider failure before streaming starts

- GIVEN the provider call fails before any bytes are sent
- WHEN the failure occurs
- THEN an HTTP error status with a generic JSON body is returned

#### Scenario: Provider failure after streaming has begun

- GIVEN SSE headers are already committed
- WHEN the provider call then fails
- THEN a terminal `error` event is emitted and the stream closes

#### Scenario: Graph-layer exception does not corrupt session state

- GIVEN an unexpected exception inside graph execution mid-turn
- WHEN the request is handled
- THEN a safe error is returned and the next request on the same `thread_id` completes normally
