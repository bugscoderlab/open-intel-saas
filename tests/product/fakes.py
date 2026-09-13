"""Test doubles for the research pipeline (ticket #24).

``DeterministicEmbedder`` returns stable vector(1536) values derived from
the input text and records every ``embed`` call, so tests can assert both
the written rows and that the pipeline passed the chunk contents. No
provider APIs are touched — the seam the ticket's acceptance criteria
require ("inject a fake/stub embedding model at the composition seam").
"""

from modules.research.application.errors import EmbeddingProviderError
from modules.research.domain.embedder import EMBEDDING_DIMENSIONS


def _deterministic_vector(text: str) -> list[float]:
    seed = (len(text) * 31 + sum(map(ord, text[:50]))) % 997 / 997.0
    return [round(seed + i * 1e-6, 6) for i in range(EMBEDDING_DIMENSIONS)]


class DeterministicEmbedder:
    """Stable 1536-dim vectors, one per input text, calls recorded."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [_deterministic_vector(text) for text in texts]


class FlakyEmbedder:
    """Fails the first ``failures`` calls with a typed provider error,
    then delegates — the retryable-failure seam."""

    def __init__(
        self,
        delegate: DeterministicEmbedder,
        *,
        failures: int = 1,
        error: str = "simulated provider outage",
    ) -> None:
        self._delegate = delegate
        self._failures = failures
        self._error = error

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._failures > 0:
            self._failures -= 1
            raise EmbeddingProviderError(self._error)
        return await self._delegate.embed(texts)
