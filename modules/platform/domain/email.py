"""Transactional email port for invitations (ticket #6 decision).

Invitation email goes through the application's own provider (Resend when
configured), never Supabase Auth SMTP. The port lives in the domain
layer so infrastructure adapters and application services can both
depend on it (plan §14.2 layering).
"""

from typing import Protocol


class TransactionalEmailProvider(Protocol):
    """Sends the invitation accept link to the invitee."""

    async def send_invitation(
        self,
        *,
        to_email: str,
        organization_name: str,
        scope: str,
        role: str,
        accept_url: str,
    ) -> None:
        """Deliver the invitation email. Raises on delivery failure."""
        ...
