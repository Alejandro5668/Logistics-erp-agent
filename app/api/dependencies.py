"""`Depends()` providers: the cached agent singleton and the `ThreadRegistry`
(design.md "Decision: Checkpointer safety via thread generation remap").

Both are process-wide singletons, not per-request objects: the agent must
stay cached across requests so its `InMemorySaver` checkpointer preserves
session continuity for a `thread_id` across turns (proposal.md Success
Criteria: "Two turns on the same `thread_id` preserve session continuity
across requests"); the registry must stay cached for the same reason — its
generation counters are only useful if every request consults the same map.
`app/api/routes/chat.py` (PR 2) wires these as `Depends(get_agent)` /
`Depends(get_thread_registry)`; integration tests override them via
`app.dependency_overrides`, never by calling `get_agent()` directly (that
would hit a real provider — see `build_agent`'s docstring / `app/agent/core.py`).
"""

from __future__ import annotations

import threading
from functools import lru_cache

from app.agent import build_agent


@lru_cache(maxsize=1)
def get_agent():
    """Build (once) and cache the F-B5 agent for the lifetime of the
    process. Zero-arg `lru_cache(maxsize=1)` is a plain memoized singleton,
    not a per-argument cache: a second call anywhere in the process returns
    the exact same object, same checkpointer.

    Deliberately calls `build_agent()` with no `model=` override — the
    production path resolves `AGENT_MODEL`/`DEFAULT_MODEL` and touches a
    real provider at first call. Tests must never call this function
    directly; monkeypatch `app.api.dependencies.build_agent` (or clear/replace
    the cache) to inject a `ScriptedChatModel` instead, mirroring
    `tests/test_agent_build.py`'s offline seam.
    """
    return build_agent()


class ThreadRegistry:
    """Maps a public, caller-supplied `thread_id` to an internal
    `{thread_id}#{generation}` used as the checkpointer's real thread id.

    Rationale (design.md E5): `durability="async"` persists the checkpoint
    and any pending writes even when a mid-turn exception propagates, so a
    failed turn can leave a thread's checkpoint holding an `AIMessage` with
    `tool_calls` and no matching `ToolMessage`s — a shape most providers
    reject. Bumping the generation on failure means the *next* request for
    that public `thread_id` gets a fresh internal thread id with no prior
    checkpoint, so a poisoned checkpoint never reaches a later turn.

    A guardrail BLOCK is NOT treated as a failure here: the middleware's own
    `jump_to: "end"` update closes the graph run cleanly (a well-formed
    final `AIMessage`, no dangling tool_calls, no tool ever executed) — see
    `app/security/middleware.py`'s `_block_update`. Only `bump()` on a
    genuine exception path quarantines a thread; `app.api.service.run_turn()`
    is the only caller of `bump()`.

    Thread-safe: a `threading.Lock` guards the generation map. FastAPI may
    run sync dependencies/handlers on worker threads even for an async app,
    so two requests touching the same public `thread_id` concurrently must
    not race on the counter.
    """

    def __init__(self) -> None:
        self._generations: dict[str, int] = {}
        self._lock = threading.Lock()

    def get_internal_thread_id(self, thread_id: str) -> str:
        """Return `{thread_id}#{generation}` for the thread's CURRENT
        generation (starts at 0, never negative, monotonically increases)."""
        with self._lock:
            generation = self._generations.get(thread_id, 0)
        return f"{thread_id}#{generation}"

    def bump(self, thread_id: str) -> None:
        """Advance `thread_id`'s generation by one. Idempotent-safe to call
        multiple times for the same failed turn; each call just advances
        further, which is harmless (the next request only ever reads the
        latest generation)."""
        with self._lock:
            self._generations[thread_id] = self._generations.get(thread_id, 0) + 1

    def current_generation(self, thread_id: str) -> int:
        """Read-only accessor for tests/introspection."""
        with self._lock:
            return self._generations.get(thread_id, 0)


_thread_registry = ThreadRegistry()


def get_thread_registry() -> ThreadRegistry:
    """Return the process-wide `ThreadRegistry` singleton."""
    return _thread_registry
