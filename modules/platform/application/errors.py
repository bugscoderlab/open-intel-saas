"""Re-exports of the domain error types (which see for the taxonomy)."""

from modules.platform.domain.errors import (
    ConflictError,
    ForbiddenError,
    InvitationEmailMismatchError,
    InvitationInvalidError,
    NotAuthenticatedError,
    NotFoundError,
    PlatformError,
    PrincipalResolutionError,
    TokenVerificationError,
)

__all__ = [
    "PlatformError",
    "NotAuthenticatedError",
    "TokenVerificationError",
    "PrincipalResolutionError",
    "NotFoundError",
    "ForbiddenError",
    "ConflictError",
    "InvitationInvalidError",
    "InvitationEmailMismatchError",
]
