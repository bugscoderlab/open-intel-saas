"""Collection fetch errors (spec #41) — typed, mapped to HTTP in one place.

Subclasses of the platform taxonomy (platform.domain.errors), so
``map_error`` in the platform API deps turns them into statuses without
any route-level knowledge: SSRF refusals are client errors (422), fetch
failures are service errors (503), quota exhaustion is a conflict (409).
"""

from modules.platform.domain.errors import (
    ConflictError,
    ServiceUnavailableError,
    ValidationError,
)


class FetchTargetNotAllowedError(ValidationError):
    """The URL (or a redirect hop) resolves to a non-public address —
    private/loopback/link-local targets are refused as SSRF."""


class FetchFailedError(ServiceUnavailableError):
    """The fetch itself failed: unreachable host, HTTP error status, or
    an oversized/undecodable response."""


class FetchQuotaExceededError(ConflictError):
    """The project's fetch quota (jobs created in the last 24h) is spent."""


class MapsConfigurationError(ServiceUnavailableError):
    """No maps provider key configured. Mirrors the embedder failure
    policy (ticket #24): misconfiguration is visible and typed, never
    silent — configure the environment and retry."""


class MapsProviderError(ServiceUnavailableError):
    """The configured maps provider failed mid-call (network, auth,
    provider-reported error). Transient cases clear on retry."""


__all__ = [
    "FetchTargetNotAllowedError",
    "FetchFailedError",
    "FetchQuotaExceededError",
    "MapsConfigurationError",
    "MapsProviderError",
]
