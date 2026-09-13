"""Object-storage port (spec #26, ticket #28) — Platform foundation layer.

Plan §9.3: files live under tenant-scoped object keys
(``organization-id/project-id/source-id/filename``); the database stores
provider/bucket/object_key/checksum — never a provider URL. Signed URLs
are generated, short-lived, and only after authorization, at request
time. The port is deliberately tiny and bytes-in/bytes-out so any
S3-compatible backend can implement it (plan §6 portability).
"""

from datetime import timedelta
from typing import Protocol


class FileStorage(Protocol):
    """The object storage boundary. Implementations are bound to one
    private bucket at construction (``bucket``); callers never choose
    buckets, which keeps tenancy a key-layout + repository concern."""

    provider: str
    bucket: str

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store an object; replaces any existing object at the key."""
        ...

    async def get(self, key: str) -> bytes:
        """Fetch an object's bytes (the file-source pipeline's read)."""
        ...

    async def delete(self, key: str) -> None:
        """Remove an object; deleting a missing key is not an error."""
        ...

    async def signed_url(self, key: str, ttl: timedelta) -> str:
        """A short-lived, pre-authorized download URL for the object."""
        ...
