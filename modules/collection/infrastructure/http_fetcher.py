"""Reference WebsiteFetcher adapter (spec #41): plain httpx with SSRF
protection. Crawl4AI and other providers come later behind the same
domain port — this module is deliberately the only network seam.

SSRF rules, applied to EVERY hop (initial URL and each redirect target):
  * scheme must be http or https;
  * literal-IP hosts (including decimal/integer forms urlparse normalizes)
    must be globally routable — private/loopback/link-local/reserved/
    multicast/unspecified addresses are refused;
  * named hosts are resolved and EVERY resolved address must be public
    (DNS revalidated per redirect hop, so a rebinding hostname cannot
    smuggle a private address in after the first check);
  * redirects are followed manually (follow_redirects=False) up to a
    fixed hop count; a missing Location or hop overflow is a typed error.

Only transport-level success (2xx/3xx-exhausted, decodable body under
the byte cap) returns a FetchedPage; everything else raises the typed
domain errors — never a raw httpx exception.
"""

import asyncio
import ipaddress
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx

from modules.collection.domain.errors import (
    FetchFailedError,
    FetchTargetNotAllowedError,
)
from modules.collection.domain.ports import FetchedPage

Resolver = Callable[[str], Awaitable[list[str]]]

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 15.0


async def _default_resolver(hostname: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(hostname, None)
    return sorted({str(info[4][0]) for info in infos})


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class HttpxWebsiteFetcher:
    """The WebsiteFetcher port over a plain httpx client.

    ``client`` and ``resolver`` are injectable so tests can substitute a
    mocked transport and a stubbed DNS without any network access.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        resolver: Resolver | None = None,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=timeout, follow_redirects=False
        )
        self._resolver = resolver or _default_resolver
        self._max_redirects = max_redirects
        self._max_bytes = max_bytes

    async def _validate_target(self, url: str) -> str:
        """Refuse non-public targets before any byte is fetched."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise FetchTargetNotAllowedError(f"refusing to fetch non-http(s) URL: {url}")
        host = parsed.hostname
        try:
            # Literal IP host (v4/v6, incl. normalized integer forms).
            ip = ipaddress.ip_address(host)
            addresses = [str(ip)]
        except ValueError:
            addresses = await self._resolver(host)
            if not addresses:
                raise FetchFailedError(f"could not resolve host: {host}")
        if any(not _is_public_ip(address) for address in addresses):
            raise FetchTargetNotAllowedError(
                f"refusing to fetch non-public address for {host}: {addresses}"
            )
        return url

    async def fetch(self, url: str) -> FetchedPage:
        current = await self._validate_target(url)
        for _ in range(self._max_redirects + 1):
            try:
                response = await self._client.get(current)
            except FetchTargetNotAllowedError:
                raise
            except httpx.HTTPError as exc:
                raise FetchFailedError(f"fetch failed: {exc}") from exc
            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("location")
                if location is None:
                    raise FetchFailedError(
                        f"redirect without Location from {current}"
                    )
                # Re-validate the redirect target from scratch: scheme,
                # host and DNS all checked again for this hop.
                current = await self._validate_target(urljoin(current, location))
                continue
            if response.status_code >= 400:
                raise FetchFailedError(
                    f"fetch failed with status {response.status_code}: {current}"
                )
            body = await response.aread()
            if len(body) > self._max_bytes:
                raise FetchFailedError(
                    f"response exceeds {self._max_bytes} byte cap: {current}"
                )
            return FetchedPage(
                url=current,
                status_code=response.status_code,
                content=body.decode("utf-8", errors="replace"),
                fetched_at=datetime.now(UTC),
            )
        raise FetchTargetNotAllowedError(
            f"more than {self._max_redirects} redirects fetching {url}"
        )
