"""The embedder port (ticket #24, spec #21): provider-agnostic text →
vector. The pipeline depends on this protocol; the composition root
wires a concrete implementation (Esperanto today, per spec #21), and the
test seam injects a deterministic fake — same mechanism, no provider
APIs touched by tests.
"""

from typing import Protocol

# plan §9: source_chunks.embedding is extensions.vector(1536). Provider
# models returning any other width are rejected with a typed error
# before the row write.
EMBEDDING_DIMENSIONS = 1536


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
