"""Supabase Storage implementation of the FileStorage port (ticket #28).

Plain httpx against the Supabase Storage HTTP API — no provider SDK in
the composition root beyond what the project already ships. The service-
role key is backend-only (plan §8.2): this class is the only storage
caller, and signed URLs are the only egress to clients.
"""

from datetime import timedelta

import httpx

from modules.platform.domain.errors import ServiceUnavailableError


class SupabaseStorage:
    """FileStorage over Supabase Storage, bound to one private bucket."""

    provider = "supabase"

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        bucket: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bucket = bucket
        self._base_url = supabase_url.rstrip("/") + "/storage/v1"
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
            },
            timeout=30,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        response = await self._client.post(
            f"/object/{self.bucket}/{key}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        if response.status_code >= 400:
            raise ServiceUnavailableError(
                f"storage put failed ({response.status_code}): {response.text[:200]}"
            )

    async def get(self, key: str) -> bytes:
        response = await self._client.get(f"/object/{self.bucket}/{key}")
        if response.status_code >= 400:
            raise ServiceUnavailableError(
                f"storage get failed ({response.status_code}): {response.text[:200]}"
            )
        return response.content

    async def delete(self, key: str) -> None:
        response = await self._client.delete(f"/object/{self.bucket}/{key}")
        if response.status_code >= 400:
            raise ServiceUnavailableError(
                f"storage delete failed ({response.status_code}): {response.text[:200]}"
            )

    async def signed_url(self, key: str, ttl: timedelta) -> str:
        response = await self._client.post(
            f"/object/sign/{self.bucket}/{key}",
            json={"expiresIn": max(1, int(ttl.total_seconds()))},
        )
        if response.status_code >= 400:
            raise ServiceUnavailableError(
                f"storage sign failed ({response.status_code}): {response.text[:200]}"
            )
        signed_path = response.json()["signedURL"]
        return f"{self._base_url}{signed_path}"
