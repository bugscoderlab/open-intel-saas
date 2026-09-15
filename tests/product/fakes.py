"""Test doubles for the research pipeline (ticket #24) and the storage
seam (ticket #28).

``DeterministicEmbedder`` returns stable vector(1536) values derived from
the input text and records every ``embed`` call, so tests can assert both
the written rows and that the pipeline passed the chunk contents. No
provider APIs are touched — the seam the ticket's acceptance criteria
require ("inject a fake/stub embedding model at the composition seam").

``RecordingFileStorage`` is the same composition-root pattern for the
FileStorage port (spec #26): objects live in memory, every call is
recorded, and signed URLs are deterministic — no real bucket is touched.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.extraction.domain.entities import ExtractionResult

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


class KeywordEmbedder:
    """Controllable 1536-dim embeddings: any text containing a keyword
    gets that keyword's axis set to 1.0, everything else 0.05 — so
    vector-nearest results are deterministic and semantically meaningful
    for search assertions (unlike the hash-based DeterministicEmbedder)."""

    def __init__(self, *keywords: str) -> None:
        self._keywords = [k.lower() for k in keywords]
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        return [
            1.0 if keyword in lowered else 0.05 for keyword in self._keywords
        ] + [0.05] * (EMBEDDING_DIMENSIONS - len(self._keywords))


class RecordingFileStorage:
    """In-memory FileStorage: records puts/deletes/sign calls, serves
    stored bytes back, and returns deterministic signed URLs."""

    provider = "recording"

    def __init__(self, bucket: str = "test-files") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}
        self.puts: list[tuple[str, str, bytes, str]] = []
        self.deletes: list[str] = []
        self.sign_calls: list[tuple[str, str]] = []

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.puts.append((self.bucket, key, data, content_type))
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError:
            raise FileNotFoundError(key) from None

    async def delete(self, key: str) -> None:
        self.deletes.append(key)
        self.objects.pop(key, None)

    async def signed_url(self, key: str, ttl: timedelta) -> str:
        self.sign_calls.append((self.bucket, key))
        return f"signed://{self.bucket}/{key}"


class FakeWebsiteFetcher:
    """Fake WebsiteFetcher port (collection, ticket #42): scripted pages
    keyed by URL, an optional exception to raise on every fetch, and a
    recording of every fetched URL. No network."""

    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.pages = pages or {}
        self.fail_with: Exception | None = None
        self.fetched: list[str] = []

    async def fetch(self, url: str):
        from modules.collection.domain.ports import FetchedPage

        self.fetched.append(url)
        if self.fail_with is not None:
            raise self.fail_with
        return FetchedPage(
            url=url,
            status_code=200,
            content=self.pages.get(url, "<html><body>default page</body></html>"),
            fetched_at=datetime.now(UTC),
        )


class FakeMapsProvider:
    """Fake MapsProvider port (collection, ticket #43): scripted
    candidates keyed by (query, location), an optional exception to
    raise on every call, and a recording of every query. No network."""

    def __init__(
        self,
        candidates: dict[tuple[str, str], list] | None = None,
    ) -> None:
        self.candidates = candidates or {}
        self.fail_with: Exception | None = None
        self.queries: list[tuple[str, str]] = []

    async def discover(self, *, query: str, location: str):
        from modules.collection.domain.ports import MapCandidate

        self.queries.append((query, location))
        if self.fail_with is not None:
            raise self.fail_with
        return [
            MapCandidate(**candidate) if isinstance(candidate, dict) else candidate
            for candidate in self.candidates.get((query, location), [])
        ]


class FakeExtractor:
    """Fake Extractor port (extraction, ticket #50): scripted results
    keyed by exact source text, an optional exception to raise on every
    call, and a recording of every extracted source text. No network,
    no provider configuration."""

    def __init__(
        self,
        results: "dict[str, ExtractionResult] | None" = None,
    ) -> None:
        from modules.extraction.domain.entities import ExtractionResult

        self._result_type = ExtractionResult
        self.results: "dict[str, ExtractionResult]" = results or {}
        self.fail_with: Exception | None = None
        self.extracted: list[str] = []

    async def extract(self, *, source_text: str, source_url: str | None = None):
        self.extracted.append(source_text)
        if self.fail_with is not None:
            raise self.fail_with
        return self.results.get(source_text, self._result_type(items=()))
