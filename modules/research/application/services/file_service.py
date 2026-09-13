"""Stored-object use cases (ticket #28, spec #26) — the storage half of
the Phase 2 backfill. Hardened validation runs before any object write;
the object put and the registry row land in the caller's transaction
(plan §9.3: the database stores provider/bucket/object_key/checksum —
never a provider URL; downloads are signed at request time, only after
authorization, which the file-source endpoints enforce with source.read).
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

from modules.platform.domain.errors import ValidationError
from modules.platform.domain.storage import FileStorage
from modules.research.domain.entities import SourceFile
from modules.research.domain.unit_of_work import ResearchUnit

# Upload contract (spec #26 assumption 5). The declared content type must
# match the extension's allowed set, and binary formats must match their
# magic bytes — both checked before anything is written to storage.
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

ALLOWED_CONTENT_TYPES: dict[str, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "txt": frozenset({"text/plain"}),
    "md": frozenset({"text/markdown", "text/plain"}),
    "csv": frozenset({"text/csv", "text/plain"}),
    "html": frozenset({"text/html"}),
}

_MAGIC_BYTES: dict[str, bytes] = {
    "pdf": b"%PDF",
}

# Short-lived download URLs: generated at request time, never persisted.
SIGNED_URL_TTL = timedelta(minutes=5)


def _sanitize_filename(filename: str) -> str:
    """Reduce to a bare basename — the key layout owns the path structure,
    so a client filename can never inject extra segments."""
    return filename.replace("\\", "/").rsplit("/", 1)[-1].strip() or "file"


def validate_upload(filename: str, content_type: str, data: bytes) -> str:
    """The hardened gate: anything rejected here has caused no side
    effects. Returns the normalized extension."""
    lowered = filename.lower()
    extension = lowered.rsplit(".", 1)[-1] if "." in lowered else ""
    if extension not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            f"file type '{extension or 'unknown'}' is not an allowed upload type"
        )
    allowed_types = ALLOWED_CONTENT_TYPES[extension]
    if content_type not in allowed_types:
        raise ValidationError(
            f"content type '{content_type}' is not allowed for '.{extension}' files"
        )
    if not data:
        raise ValidationError("file is empty")
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            f"file exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB upload limit"
        )
    magic = _MAGIC_BYTES.get(extension)
    if magic is not None and not data.startswith(magic):
        raise ValidationError(
            f"file content does not match the '.{extension}' format"
        )
    return extension


def build_object_key(
    *,
    organization_id: UUID,
    project_id: UUID,
    source_id: UUID | None,
    filename: str,
) -> str:
    """Plan §9.3 layout: organization-id/project-id/source-id/filename."""
    source_segment = str(source_id) if source_id is not None else "unlinked"
    return (
        f"{organization_id}/{project_id}/{source_segment}"
        f"/{_sanitize_filename(filename)}"
    )


async def save_file(
    unit: ResearchUnit,
    storage: FileStorage,
    *,
    organization_id: UUID,
    project_id: UUID,
    source_id: UUID | None,
    filename: str,
    content_type: str,
    data: bytes,
    created_by: UUID,
) -> SourceFile:
    """Validate, store, register — in that order, with the registry write
    in the caller's transaction. The object key repeats the tenant scope
    so storage-level listing is tenant-partitioned too."""
    validate_upload(filename, content_type, data)
    object_key = build_object_key(
        organization_id=organization_id,
        project_id=project_id,
        source_id=source_id,
        filename=filename,
    )
    await storage.put(object_key, data, content_type)
    source_file = SourceFile(
        id=uuid4(),
        organization_id=organization_id,
        project_id=project_id,
        source_id=source_id,
        provider=storage.provider,
        bucket=storage.bucket,
        object_key=object_key,
        checksum=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        content_type=content_type,
        created_by=created_by,
    )
    await unit.source_files.create(source_file)
    return source_file


async def signed_url_for(
    storage: FileStorage,
    source_file: SourceFile,
    *,
    ttl: timedelta = SIGNED_URL_TTL,
) -> str:
    """The only download egress: a short-lived URL from the storage port,
    produced after the caller has authorized (the endpoints gate this
    behind source.read)."""
    return await storage.signed_url(source_file.object_key, ttl)
