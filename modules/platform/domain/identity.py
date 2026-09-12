"""Provider-neutral identity at the API boundary (plan §7.3).

The browser never submits an Application user ID: every authenticated
request derives its principal from a verified JWT, and the Application
user is resolved through ``user_identities`` (ticket #3 acceptance).

The IdentityProvider protocol lives in the domain layer so both the
application layer and infrastructure adapters can depend on it without
violating the layering contracts (plan §14.2).
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from modules.platform.domain.errors import (
    PrincipalResolutionError,
    TokenVerificationError,
)


@dataclass(frozen=True)
class Principal:
    """Who is calling: verified claims + the resolved Application user.

    Attributes:
        provider: Identity provider name (``"supabase"`` for the first
            adapter; the field keeps the principal provider-neutral).
        subject: The provider's own subject (the JWT ``sub`` claim).
        app_user_id: The product-owned Application user the subject maps
            to, resolved through ``user_identities``.
        email: Email from the token claims.
        email_confirmed: Whether the provider has confirmed the email.
    """

    provider: str
    subject: str
    app_user_id: UUID
    email: str
    email_confirmed: bool


class IdentityProvider(Protocol):
    """Verifies a bearer token and resolves the Application user principal."""

    async def verify_token(self, token: str) -> Principal:
        """Return the principal for a verified token.

        Raises:
            TokenVerificationError: The token cannot be verified (401).
            PrincipalResolutionError: The token verified but the subject
                maps to no Application user (403).
        """
        ...


__all__ = [
    "Principal",
    "IdentityProvider",
    "TokenVerificationError",
    "PrincipalResolutionError",
]
