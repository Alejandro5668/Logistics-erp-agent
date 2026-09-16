"""Offline test double for `create_agent`'s `model` parameter (F-B5).

`ScriptedChatModel` emits one pre-scripted `AIMessage` per model step and
overrides `bind_tools` — required, since `BaseChatModel.bind_tools` raises
`NotImplementedError` by default (verified against the installed
`langchain-core`, see design.md), and `create_agent` calls
`request.model.bind_tools(tools, tool_choice=...)` before the first token.

Unlike `langchain_core...fake_chat_models.FakeMessagesListChatModel`, which
*cycles* its response list, this double uses **strict exhaustion**: calling
`_generate` past the end of `responses` raises `AssertionError` instead of
silently re-emitting an earlier turn. That is what turns "the agent called
the right tools in the right order" into a real assertion — a mis-scripted
test fails loudly instead of passing by accidental repetition.

This test double proves *wiring* only (tool routing, guardrail
interception, checkpoint replay) — never real LLM reasoning quality. No
network call, no credentials, ever.
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    """Emits a scripted `AIMessage` per model step. No network, no credentials."""

    responses: list[BaseMessage]
    index: int = 0
    bound_tools: list = Field(default_factory=list)
    seen: list = Field(default_factory=list)

    def bind_tools(
        self,
        tools,
        *,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ):
        """MUST override: the base implementation raises `NotImplementedError`.

        Records the bound tools (for wiring assertions) and returns `self` —
        `ScriptedChatModel` is already a `Runnable`, so no wrapper is needed.
        """
        self.bound_tools = list(tools)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Return the next scripted message, recording `messages` for replay
        assertions. Raises `AssertionError` — never cycles — once `responses`
        is exhausted, so an unscripted step fails the test loudly."""
        self.seen.append(list(messages))
        if self.index >= len(self.responses):
            raise AssertionError(
                "ScriptedChatModel exhausted — agent took an unscripted step"
            )
        message = self.responses[self.index]
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"


def tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    """Build an `AIMessage` that proposes exactly one tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def final(text: str) -> AIMessage:
    """Build a plain final-answer `AIMessage` with no tool calls."""
    return AIMessage(content=text)
