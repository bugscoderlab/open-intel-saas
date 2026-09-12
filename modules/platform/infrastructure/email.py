"""Transactional email providers for invitations (ticket #6 decision).

Dev default logs to the console; production sends through Resend's API
with plain httpx (no SDK dependency). Tests substitute RecordingEmailProvider.
"""

import httpx


class ConsoleEmailProvider:
    """Dev provider: the accept link lands in the API log, not an inbox."""

    async def send_invitation(
        self,
        *,
        to_email: str,
        organization_name: str,
        scope: str,
        role: str,
        accept_url: str,
    ) -> None:
        print(
            "[invitation email]\n"
            f"  to:       {to_email}\n"
            f"  org:      {organization_name}\n"
            f"  scope:    {scope} ({role})\n"
            f"  accept:   {accept_url}"
        )


class ResendEmailProvider:
    """Sends the invitation through Resend's transactional API."""

    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._http = http or httpx.AsyncClient(timeout=15)

    async def send_invitation(
        self,
        *,
        to_email: str,
        organization_name: str,
        scope: str,
        role: str,
        accept_url: str,
    ) -> None:
        response = await self._http.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "from": "Open Intel <invitations@open-intel.dev>",
                "to": [to_email],
                "subject": f"You have been invited to {organization_name}",
                "text": (
                    f"You were invited to {organization_name} "
                    f"({scope} role: {role}). Accept the invitation here:\n\n"
                    f"{accept_url}\n\n"
                    "This link is single-use and expires in 7 days."
                ),
            },
        )
        response.raise_for_status()


class RecordingEmailProvider:
    """Test provider: records sends instead of delivering them."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_invitation(
        self,
        *,
        to_email: str,
        organization_name: str,
        scope: str,
        role: str,
        accept_url: str,
    ) -> None:
        self.sent.append(
            {
                "to_email": to_email,
                "organization_name": organization_name,
                "scope": scope,
                "role": role,
                "accept_url": accept_url,
            }
        )
