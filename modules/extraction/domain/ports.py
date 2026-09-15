"""Domain ports for extraction (spec #49)."""

from typing import Protocol, runtime_checkable

from modules.extraction.domain.entities import ExtractionResult


@runtime_checkable
class Extractor(Protocol):
    """Turns one untrusted source text into a validated structured
    result. Implementations: infrastructure LLM adapter (reference),
    fakes in tests. Raises typed Extraction* errors only."""

    async def extract(
        self, *, source_text: str, source_url: str | None = None
    ) -> ExtractionResult: ...
