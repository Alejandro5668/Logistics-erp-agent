"""Agent factory: the one composition root wiring F-B1..F-B4's tools, F-B5's
two new action tools, F-B4's security middleware, and a checkpointer into a
single `create_agent` ReAct instance.

No new abstraction over LangChain: `create_agent` already supplies the ReAct
loop, the middleware slot, and the checkpointer — per architecture-patterns
Decision Gates, this is composition, not a new integration (see design.md).

Call signature verified against the installed `langchain==1.4.0`
(`langchain/agents/factory.py`): the prompt keyword is `system_prompt`, NOT
`prompt`/`state_modifier`.
"""

from __future__ import annotations

import os
from typing import Optional, Union

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.prompt import SYSTEM_PROMPT
from app.rag.store import search_regulations
from app.security import build_security_middleware
from app.tools import (
    calculate_tax_discrepancy,
    create_erp_adjustment,
    get_erp_data,
    notify_human,
)

DEFAULT_MODEL = "azure_openai:gpt-4o"

# Single source of truth for wiring *and* for the "exactly 5 tools"
# assertion (design.md: a CompiledStateGraph exposes no clean tool list).
AGENT_TOOLS = (
    get_erp_data,
    calculate_tax_discrepancy,
    search_regulations,
    create_erp_adjustment,
    notify_human,
)


def build_agent(
    model: Optional[Union[str, BaseChatModel]] = None,
    checkpointer=None,
):
    """Build the F-B5 ReAct agent: the 5 named tools, the F-B4 security
    middleware, and a thread-scoped checkpointer.

    `model` accepts a provider-prefixed string (e.g. `"azure_openai:gpt-4o"`),
    a pre-built `BaseChatModel` — the test seam, mirroring F-B3's
    `_set_embedding_function` — or `None`, which resolves `AGENT_MODEL` from
    the environment and falls back to `DEFAULT_MODEL`. `app/agent/core.py`
    never hardcodes one provider (spec's Model-Agnostic Model Parameter
    requirement). A string model is resolved *eagerly* by `create_agent` via
    `init_chat_model`, so the zero-argument construction path touches the
    provider at build time and requires credentials.

    `checkpointer` defaults to a fresh `InMemorySaver()` **per call**, never
    a module-level singleton — a shared saver would leak turns between
    independently built agents and between tests (design.md). It is keyed
    by `thread_id` alone; `role` is supplied per-invocation via `context`,
    never bound into the thread/session (spec's Thread-Scoped Session Memory
    requirement).
    """
    return create_agent(
        model=model or os.environ.get("AGENT_MODEL") or DEFAULT_MODEL,
        tools=list(AGENT_TOOLS),
        system_prompt=SYSTEM_PROMPT,
        middleware=[build_security_middleware()],
        checkpointer=checkpointer or InMemorySaver(),
    )
