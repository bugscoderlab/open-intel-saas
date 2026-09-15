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
