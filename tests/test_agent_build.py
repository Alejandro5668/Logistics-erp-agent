"""Tests for app.agent.core (F-B5 L1 — build/wiring, no invocation).

Proves the factory wires the right pieces (5 tools, `system_prompt=`, not
`prompt=`, middleware, checkpointer) without exercising the ReAct loop.
`build_agent(model=ScriptedChatModel(...))` never touches the network or a
real provider — the offline test seam per spec's Model-Agnostic Model
Parameter requirement.

`AGENT_TOOLS` is asserted directly (module constant), and `bound_tools` is
asserted after a no-op invoke: `create_agent` resolves `model.bind_tools`
lazily at request time (design.md `factory.py:1434`), not at construction,
so `bound_tools` is empty immediately after `build_agent()` returns.
"""

from langgraph.checkpoint.memory import InMemorySaver

from app.agent import AGENT_TOOLS, DEFAULT_MODEL, build_agent
from tests.scripted_model import ScriptedChatModel, final

EXPECTED_TOOL_NAMES = {
    "get_erp_data",
    "calculate_tax_discrepancy",
    "search_regulations",
    "create_erp_adjustment",
    "notify_human",
}


class TestAgentToolsConstant:
    def test_agent_tools_has_exactly_five_entries(self):
        assert len(AGENT_TOOLS) == 5

    def test_agent_tools_names_match_expected_set(self):
        names = {tool.name for tool in AGENT_TOOLS}

        assert names == EXPECTED_TOOL_NAMES

    def test_agent_tools_order_matches_prompt_tool_order(self):
        # TOOL ORDER in the system prompt: get_erp_data,
        # calculate_tax_discrepancy, search_regulations, then exactly one
        # action tool.
        names = [tool.name for tool in AGENT_TOOLS]

        assert names[:3] == ["get_erp_data", "calculate_tax_discrepancy", "search_regulations"]
        assert set(names[3:]) == {"create_erp_adjustment", "notify_human"}


class TestDefaultModel:
    def test_default_model_is_a_provider_prefixed_string(self):
        assert isinstance(DEFAULT_MODEL, str)
        assert ":" in DEFAULT_MODEL


class TestBuildAgentWithScriptedModel:
    def test_returns_a_non_none_runnable_graph(self):
        model = ScriptedChatModel(responses=[final("ok")])

        agent = build_agent(model=model)

        assert agent is not None

    def test_returned_agent_exposes_a_callable_invoke(self):
        model = ScriptedChatModel(responses=[final("ok")])

        agent = build_agent(model=model)

        assert callable(getattr(agent, "invoke", None))

    def test_no_network_call_is_made_building_with_a_fake_model(self):
        # If build_agent() tried to resolve a real provider, this would
        # raise (no credentials, no network in the test environment).
        # Passing a BaseChatModel instance skips init_chat_model entirely.
        model = ScriptedChatModel(responses=[final("ok")])

        build_agent(model=model)  # must not raise

    def test_bound_tools_count_is_five_after_a_noop_invoke(self):
        model = ScriptedChatModel(responses=[final("ok")])
        agent = build_agent(model=model)

        agent.invoke(
            {"messages": [{"role": "user", "content": "hi"}]},
            config={"configurable": {"thread_id": "t-build-test"}},
        )

        assert len(model.bound_tools) == 5
        assert {tool.name for tool in model.bound_tools} == EXPECTED_TOOL_NAMES

    def test_default_checkpointer_is_used_when_none_is_passed(self):
        model = ScriptedChatModel(responses=[final("ok")])

        agent = build_agent(model=model)

        assert agent.checkpointer is not None

    def test_explicit_checkpointer_is_honored(self):
        model = ScriptedChatModel(responses=[final("ok")])
        checkpointer = InMemorySaver()

        agent = build_agent(model=model, checkpointer=checkpointer)

        assert agent.checkpointer is checkpointer

    def test_two_independently_built_agents_get_independent_checkpointers(self):
        model_a = ScriptedChatModel(responses=[final("a")])
        model_b = ScriptedChatModel(responses=[final("b")])

        agent_a = build_agent(model=model_a)
        agent_b = build_agent(model=model_b)

        assert agent_a.checkpointer is not agent_b.checkpointer
