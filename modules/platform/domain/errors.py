"""Service-layer error types, shared by every layer.

Domain code is the lowest layer, so errors raised by infrastructure
adapters (e.g. token verification) are declared here — inner layers
never import infrastructure, and infrastructure never imports the
application layer (import-linter contracts, plan §14.2).
"""


class PlatformError(Exception):
    """Base class for every service-layer error."""


class NotAuthenticatedError(PlatformError):
    """No bearer token, or the token failed verification."""


class TokenVerificationError(PlatformError):
    """Expired, malformed, or wrongly signed token (HTTP 401)."""


class PrincipalResolutionError(PlatformError):
    """Token verified, but the subject maps to no Application user."""


class NotFoundError(PlatformError):
    """The target does not exist — the tenant-safe answer to guessed IDs."""


class ForbiddenError(PlatformError):
    """The principal is known but does not hold the required Permission."""


class ConflictError(PlatformError):
    """The request conflicts with current state (duplicate invite, etc.)."""


class InvitationInvalidError(PlatformError):
    """Token unknown, expired, or already consumed."""


class InvitationEmailMismatchError(PlatformError):
    """Session email does not equal the invited email."""
