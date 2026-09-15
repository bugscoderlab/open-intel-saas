"""The WebsiteFetcher port (spec #41): the module's only network seam.

Domain-pure: a Protocol plus the FetchedPage value object. The reference
adapter is infrastructure/http_fetcher.py (plain httpx with SSRF
protection); tests substitute a fake at exactly this seam. Implementations
raise the typed domain errors — never transport exceptions.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class FetchedPage:
    """One fetched page: the final URL after redirects, the raw text,
    and when the capture happened (becomes the snapshot's captured_at)."""

    url: str
    status_code: int
    content: str
    fetched_at: datetime


class WebsiteFetcher(Protocol):
    """Fetch one URL and return the raw page.

    Raises FetchTargetNotAllowedError for non-public targets (SSRF,
    revalidated across every redirect hop) and FetchFailedError for
    transport/HTTP failures — both typed domain errors.
    """

    async def fetch(self, url: str) -> FetchedPage: ...


@dataclass(frozen=True)
class MapCandidate:
    """One business returned by a maps discovery query — data only,
    never persisted (spec #41 assumption 3; adding a candidate stays
    the Phase 3 manual competitor flow)."""

    name: str
    address: str | None
    website: str | None
    provider_metadata: dict


class MapsProvider(Protocol):
    """Discover candidate businesses by industry/query + location.

    The reference adapter is infrastructure/google_places.py (env-keyed,
    typed "not configured" error when the key is unset — the embedder
    failure policy); tests substitute a fake at exactly this seam.
    Implementations raise the typed domain errors — never transport
    exceptions.
    """

    async def discover(self, *, query: str, location: str) -> list[MapCandidate]: ...
