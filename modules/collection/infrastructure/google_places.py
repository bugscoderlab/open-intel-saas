"""Reference MapsProvider adapter (spec #41): Google Places Text Search,
keyed from the environment through Settings. Mirrors the embedder
failure policy (ticket #24): unconfigured is fine at boot — ``discover``
raises the typed MapsConfigurationError per call, so misconfiguration is
visible, never silent. Provider-reported failures (bad key, quota,
denied) raise the typed MapsProviderError; never a raw httpx exception.

Text Search returns name/address/place metadata but not websites (those
need a per-place Details call); ``website`` stays None here and the
field is filled by a later enrichment step behind the same port.
"""

import httpx

from modules.collection.domain.errors import (
    MapsConfigurationError,
    MapsProviderError,
)
from modules.collection.domain.ports import MapCandidate

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DEFAULT_TIMEOUT_SECONDS = 15.0


class GooglePlacesMapsProvider:
    """The MapsProvider port over the Google Places Text Search API.

    ``client`` is injectable so tests can substitute a mocked transport
    without any network access.
    """

    def __init__(
        self,
        api_key: str = "",
        client: httpx.AsyncClient | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def discover(self, *, query: str, location: str) -> list[MapCandidate]:
        if not self._api_key:
            raise MapsConfigurationError(
                "maps provider is not configured"
                " (set OPEN_INTEL_MAPS_API_KEY and restart)"
            )
        try:
            response = await self._client.get(
                TEXT_SEARCH_URL,
                params={"query": f"{query} in {location}", "key": self._api_key},
            )
        except httpx.HTTPError as exc:
            raise MapsProviderError(f"maps provider request failed: {exc}") from exc
        if response.status_code != 200:
            raise MapsProviderError(
                f"maps provider returned status {response.status_code}"
            )
        payload = response.json()
        status = payload.get("status", "UNKNOWN")
        if status not in ("OK", "ZERO_RESULTS"):
            raise MapsProviderError(
                f"maps provider error {status}: {payload.get('error_message', '')}"
            )
        return [
            MapCandidate(
                name=result.get("name", ""),
                address=result.get("formatted_address"),
                website=None,  # Text Search does not return websites
                provider_metadata={
                    "provider": "google_places",
                    "place_id": result.get("place_id", ""),
                    "rating": result.get("rating"),
                    "user_ratings_total": result.get("user_ratings_total"),
                    "types": result.get("types", []),
                },
            )
            for result in payload.get("results", [])
        ]
