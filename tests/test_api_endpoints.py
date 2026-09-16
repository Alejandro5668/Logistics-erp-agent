"""TestClient integration suite for F-B6 PR 2: the first place the WHOLE
system (F-B1..F-B6) is exercised end-to-end through real HTTP requests.

Per `app/api/dependencies.py`'s own docstring guidance: every test overrides
`app.dependency_overrides[get_agent]` (and `get_thread_registry`, for
isolation between tests) — never calls `get_agent()` directly, which would
build a real provider via `build_agent()` with no `model=` override.

Two families of test doubles are used, matching the two things this suite
must prove:

- `_FakeAstreamAgent` (duplicated from `tests/test_api_service.py`'s own
  `_ScriptedAstreamAgent` — same rationale: this module owns zero
  HTTP-router-vs-service coupling, and a shared import would blur which
  layer a failing test actually broke) — a minimal `.astream()` double for
  the two error-window tests (4.3), where only the failure *timing* matters,
  not real agent wiring.
- The REAL `build_agent()` wired with F-B5's `ScriptedChatModel` (via
  `erp_db` / `regulations_index`, exactly like `tests/test_agent_flow.py`)
  for the endpoint-shape, role/guardrail, and thread-continuity tests (4.1,
  4.2, 4.6) — these need the real graph, the real security middleware, and
  (for 4.6) the real ERP tool, to prove the full system's wiring through
  HTTP, not just `run_turn()` in isolation (already covered by
  `tests/test_api_service.py`, PR 1).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app.agent import build_agent
from app.api.app import create_app
from app.api.dependencies import ThreadRegistry, get_agent, get_thread_registry
from tests.scripted_model import ScriptedChatModel, final, tool_call


def _client_with_agent(agent, registry: ThreadRegistry | None = None) -> TestClient:
    """Build a fresh app + `TestClient`, overriding `get_agent` (and
    `get_thread_registry`, for per-test isolation) with the given double —
    never a real `build_agent()` call with no `model=` override."""
    app = create_app()
    app.dependency_overrides[get_agent] = lambda: agent
    app.dependency_overrides[get_thread_registry] = lambda: registry or ThreadRegistry()
    return TestClient(app)


class _FakeAstreamAgent:
    """Minimal `.astream()` test double: yields pre-scripted `updates`-mode
    chunks, or raises after N chunks. See module docstring for the
    duplication rationale (mirrors `tests/test_api_service.py`'s
    `_ScriptedAstreamAgent`)."""

    def __init__(self, chunks: list[dict] | None = None, *, raise_exc: Exception | None = None):
        self._chunks = chunks or []
        self._raise_exc = raise_exc

    def astream(self, *args, **kwargs):
        return self._stream()

    async def _stream(self):
        for chunk in self._chunks:
            yield chunk
        if self._raise_exc is not None:
            raise self._raise_exc


def _sse_events(text: str) -> list[tuple[str, str]]:
    """Parse a raw SSE body into `(event_name, data_json_text)` pairs."""
    events: list[tuple[str, str]] = []
    for frame in text.strip("\n").split("\n\n"):
        if not frame:
            continue
        lines = frame.split("\n")
        event_line = next((line for line in lines if line.startswith("event: ")), "")
        data_line = next((line for line in lines if line.startswith("data: ")), "")
        events.append((event_line[len("event: "):], data_line[len("data: "):]))
    return events


# ---------------------------------------------------------------------------
# 4.1 — Both endpoints reachable, correctly-shaped responses
# ---------------------------------------------------------------------------


class TestChatEndpointReachableAndShaped:
    def test_chat_sse_stream_ends_in_one_terminal_event(self):
        agent = _FakeAstreamAgent(chunks=[{"model": {"messages": [AIMessage(content="hello there")]}}])
        client = _client_with_agent(agent)

        response = client.post("/chat", json={"message": "hi", "thread_id": "t1", "role": "ADMIN"})

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(response.text)
        assert [name for name, _ in events] == ["content", "done"]

    def test_chat_sync_returns_200_with_chat_response_shape(self):
        agent = _FakeAstreamAgent(chunks=[{"model": {"messages": [AIMessage(content="hello there")]}}])
        client = _client_with_agent(agent)

        response = client.post("/chat/sync", json={"message": "hi", "thread_id": "t1", "role": "ADMIN"})

        assert response.status_code == 200
        body = response.json()
        assert body == {"content": "hello there", "thread_id": "t1", "status": "ok"}

    def test_chat_malformed_body_returns_422_no_stream_opened(self):
        agent = _FakeAstreamAgent()
        client = _client_with_agent(agent)

        response = client.post("/chat", json={"message": "hi"})  # missing thread_id

        assert response.status_code == 422

    def test_chat_sync_malformed_body_returns_422(self):
        agent = _FakeAstreamAgent()
        client = _client_with_agent(agent)

        response = client.post("/chat/sync", json={"thread_id": "t1"})  # missing message

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4.2 — Role/guardrail integration: EMPLOYEE blocked vs ADMIN succeeds
# ---------------------------------------------------------------------------


def _restricted_adjustment_response() -> AIMessage:
    """A `create_erp_adjustment` proposal whose `reason` names a restricted
    field ("salary", minimum role `FINANCE_MANAGER`) — mirrors
    `tests/test_agent_flow.py::TestL4GuardrailMidLoop`."""
    return tool_call(
        "create_erp_adjustment",
        {
            "order_id": "ORD-1001",
            "adjustment_amount": 10.0,
            "reason": "salary discrepancy adjustment",
        },
        "call-1",
    )


class TestRoleGuardrailIntegration:
    def test_employee_role_is_blocked_with_terminal_blocked_event(self, erp_db, regulations_index):
        model = ScriptedChatModel(responses=[_restricted_adjustment_response()])
        agent = build_agent(model=model)
        client = _client_with_agent(agent)

        response = client.post(
            "/chat", json={"message": "adjust ORD-1001", "thread_id": "t-employee", "role": "EMPLOYEE"}
        )

        events = _sse_events(response.text)
        assert [name for name, _ in events] == ["blocked"]
        assert "salary" not in events[0][1]  # generic safe message, no field name leaked

    def test_admin_role_succeeds_with_terminal_done_event(self, erp_db, regulations_index):
        model = ScriptedChatModel(
            responses=[_restricted_adjustment_response(), final("Ajuste aplicado.")]
        )
        agent = build_agent(model=model)
        client = _client_with_agent(agent)

        response = client.post(
            "/chat", json={"message": "adjust ORD-1001", "thread_id": "t-admin", "role": "ADMIN"}
        )

        events = _sse_events(response.text)
        event_names = [name for name, _ in events]
        assert "blocked" not in event_names
        assert event_names[-1] == "done"


# ---------------------------------------------------------------------------
# 4.3 — Error-window tests
# ---------------------------------------------------------------------------


class TestErrorWindows:
    def test_provider_failure_before_first_byte_returns_http_502_or_503(self):
        agent = _FakeAstreamAgent(chunks=[], raise_exc=TimeoutError("provider timed out"))
        client = _client_with_agent(agent)

        response = client.post("/chat", json={"message": "hi", "thread_id": "t1", "role": "ADMIN"})

        assert response.status_code in (502, 503)
        body = response.json()
        assert "timed out" not in body["message"].lower()  # no provider internals leaked

    def test_provider_failure_before_first_byte_on_sync_endpoint_also_maps_to_http_error(self):
        agent = _FakeAstreamAgent(chunks=[], raise_exc=ValueError("graph exploded"))
        client = _client_with_agent(agent)

        response = client.post("/chat/sync", json={"message": "hi", "thread_id": "t1", "role": "ADMIN"})

        assert response.status_code == 502

    def test_provider_failure_after_headers_sent_yields_terminal_error_sse_event(self):
        agent = _FakeAstreamAgent(
            chunks=[{"model": {"messages": [AIMessage(content="partial")]}}],
            raise_exc=ConnectionError("dropped"),
        )
        client = _client_with_agent(agent)

        response = client.post("/chat", json={"message": "hi", "thread_id": "t1", "role": "ADMIN"})

        # The status code cannot change after headers are committed: 200 is
        # already sent, and the failure surfaces as a terminal SSE frame.
        assert response.status_code == 200
        events = _sse_events(response.text)
        assert [name for name, _ in events] == ["content", "error"]
        import json as _json

        error_payload = _json.loads(events[-1][1])
        assert error_payload["code"] == "provider_unavailable"
        assert "dropped" not in error_payload["message"].lower()


# ---------------------------------------------------------------------------
# 4.6 — Thread continuity across sequential HTTP requests
# ---------------------------------------------------------------------------


class TestThreadContinuity:
    def test_second_turn_reuses_first_turns_tool_result_without_recalling_it(
        self, erp_db, regulations_index
    ):
        # Mirrors tests/test_agent_flow.py::TestL4MemoryContinuity, but
        # driven entirely through HTTP requests on the same thread_id.
        model = ScriptedChatModel(
            responses=[
                tool_call("get_erp_data", {"order_id": "ORD-1001"}, "call-1"),
                final("ORD-1001: net 1000.00, tax 210.00, region EU-ES."),
                final("As I found before, ORD-1001 is in region EU-ES."),
            ]
        )
        agent = build_agent(model=model)
        client = _client_with_agent(agent)

        turn_one = client.post(
            "/chat/sync",
            json={"message": "look up ORD-1001", "thread_id": "t-continuity", "role": "ADMIN"},
        )
        turn_two = client.post(
            "/chat/sync",
            json={
                "message": "remind me which region that was",
                "thread_id": "t-continuity",
                "role": "ADMIN",
            },
        )

        assert turn_one.status_code == 200
        assert turn_two.status_code == 200
        assert turn_one.json()["content"] == "ORD-1001: net 1000.00, tax 210.00, region EU-ES."
        assert turn_two.json()["content"] == "As I found before, ORD-1001 is in region EU-ES."

        # Exactly 3 scripted responses total were consumed across both
        # turns (tool_call + final for turn 1, one final for turn 2) — the
        # ScriptedChatModel raises AssertionError on any unscripted step, so
        # this proves get_erp_data was NOT re-invoked on turn 2.
        assert model.index == 3
        assert any(isinstance(m, ToolMessage) for m in model.seen[-1])
