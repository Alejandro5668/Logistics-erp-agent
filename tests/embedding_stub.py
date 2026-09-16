"""Deterministic, offline embedding function for RAG tests.

Chroma duck-types its `EmbeddingFunction` protocol: any object with a
`__call__(self, input)` method returning one fixed-length vector per input
text qualifies. `DefaultEmbeddingFunction` (all-MiniLM-L6-v2 via ONNX) would
download a model on first use, which is unacceptable in tests. This stub
never touches the network and never touches `DefaultEmbeddingFunction`.

Uses a hashed bag-of-words: every token is hashed with `sha256` (NOT the
built-in `hash()`, which is randomized per-process via PYTHONHASHSEED and
would make embeddings non-deterministic across test runs) into a fixed
64-dim vector, accumulated per text and L2-normalized. This keeps lexical
similarity meaningful enough that "tolerancia" ranks the tolerance snippets
above unrelated ones, while staying identical across processes and runs.
"""

from __future__ import annotations

import hashlib
import math

VECTOR_DIM = 64

# High-frequency Spanish function words, excluded so bag-of-words similarity
# reflects shared *content* vocabulary (e.g. "tolerancia", "impositivo")
# instead of shared grammar every snippet has regardless of topic.
_STOPWORDS = frozenset(
    "de en el la los las al del para con sin su sus lo un una y o "
    "que es se aplicable durante desde toda todos ejercicio".split()
)


class StubEmbeddingFunction:
    """Deterministic offline stand-in for Chroma's DefaultEmbeddingFunction."""

    def __call__(self, input: list[str]) -> list[list[float]]:
        # Parameter name MUST be `input` — chromadb validates the embedding
        # function signature and rejects a differently-named parameter.
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        # Feature-hashing bag-of-words: each content token increments exactly
        # one dimension (chosen deterministically via sha256), so cosine
        # similarity between two texts tracks their shared-token overlap —
        # real lexical similarity, not hash noise. Shared vocabulary (e.g.
        # the near-identical "tolerancia" wording across 2022/2023/2024)
        # pulls those vectors close together; unrelated topics do not.
        vector = [0.0] * VECTOR_DIM
        tokens = [t for t in text.lower().split() if t not in _STOPWORDS]
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % VECTOR_DIM
            vector[index] += 1.0

        norm = math.sqrt(sum(component**2 for component in vector))
        if norm == 0.0:
            return vector
        return [component / norm for component in vector]
