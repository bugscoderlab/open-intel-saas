"""Storage service seam (ticket #28, spec #26, Phase 2 backfill 1/3).

The registry table (research.source_files) is research-owned (plan §14.4);
the FileStorage port is platform foundation (plan §14.1). These tests sit
below the HTTP boundary — the upload/download endpoints land with ticket
#29 — and drive the application service directly against the managed
project with a recording fake at the storage seam (same composition-root
pattern as the deterministic embedder, ticket #24): no real bucket is
touched.

Acceptance coverage: tenant-scoped key layout (plan §9.3), registry row
content (checksum/size/content_type), hardened validation rejecting
before any object write, and signed URLs coming from the port.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from modules.platform.domain.errors import ValidationError
from modules.research.application.services import file_service
from modules.research.infrastructure.unit_of_work import SqlResearchUnit
from tests.product.conftest import TestUser, auth_headers
from tests.product.fakes import RecordingFileStorage
from tests.product.research_helpers import (
    create_text_source,
    new_notebook,
    new_project,
)


@pytest_asyncio.fixture
async def owner(user_factory) -> TestUser:
    return await user_factory("file-owner")


@pytest_asyncio.fixture
async def storage() -> RecordingFileStorage:
    return RecordingFileStorage()


@pytest_asyncio.fixture
async def unit_factory(settings) -> AsyncIterator:
    """A research unit of work over the managed project (the service's
    transaction), disposed after the test like the drain fixture does."""
    from modules.platform.infrastructure.db import create_engine

    engine = create_engine(settings.database_dsn)

    async def _make() -> SqlResearchUnit:
        return SqlResearchUnit(engine)

    yield _make
    await engine.dispose()


async def _app_user_id(api, user: TestUser) -> str:
    response = await api.get("/me", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()["app_user_id"]


async def _registry_row(settings, source_file_id: str) -> dict | None:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        row = await conn.fetchrow(
            "select organization_id, project_id, source_id, provider, bucket,"
            " object_key, checksum, size_bytes, content_type, created_by"
            " from research.source_files where id = $1::uuid",
            source_file_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def _scoped_get(
    unit_factory, organization_id, project_id, source_file_id
):
    async with await unit_factory() as unit:
        return await unit.source_files.get(organization_id, project_id, source_file_id)


async def test_store_valid_file_registers_tenant_scoped_object(
    api, owner: TestUser, org: str, settings, storage, unit_factory
) -> None:
    project_id = await new_project(api, owner, org)
    notebook_id = await new_notebook(api, owner, project_id)
    created_by = await _app_user_id(api, owner)
    # A real source row: the registry references research.sources, and
    # this is the shape ticket #29 uses (file attached to its source).
    source = await create_text_source(api, owner, project_id, notebook_id, "x")
    source_id = uuid.UUID(source["id"])
    data = b"Full grooming: RM88, September.\n"

    async with await unit_factory() as unit:
        source_file = await file_service.save_file(
            unit,
            storage,
            organization_id=uuid.UUID(org),
            project_id=uuid.UUID(project_id),
            source_id=source_id,
            filename="prices.txt",
            content_type="text/plain",
            data=data,
            created_by=uuid.UUID(created_by),
        )
        await unit.commit()

    # §9.3 key layout: organization-id/project-id/source-id/filename
    assert storage.puts, "expected the storage port to receive a put"
    (bucket, key, put_data, put_type) = storage.puts[0]
    assert put_data == data
    assert put_type == "text/plain"
    assert key == f"{org}/{project_id}/{source_id}/prices.txt"
    assert bucket == storage.bucket

    row = await _registry_row(settings, str(source_file.id))
    assert row is not None
    assert str(row["organization_id"]) == org
    assert str(row["project_id"]) == project_id
    assert str(row["source_id"]) == str(source_id)
    assert row["object_key"] == key
    assert row["checksum"] == hashlib.sha256(data).hexdigest()
    assert row["size_bytes"] == len(data)
    assert row["content_type"] == "text/plain"
    assert row["provider"] == storage.provider

    # The scope is a query predicate, never a post-filter: another org
    # asking for the same id gets nothing.
    assert (
        await _scoped_get(
            unit_factory, uuid.uuid4(), uuid.uuid4(), source_file.id
        )
        is None
    )


async def test_rejects_oversize_file_before_any_write(
    api, owner: TestUser, org: str, storage, unit_factory
) -> None:
    project_id = await new_project(api, owner, org)
    created_by = await _app_user_id(api, owner)
    data = b"x" * (file_service.MAX_FILE_SIZE_BYTES + 1)

    with pytest.raises(ValidationError):
        async with await unit_factory() as unit:
            await file_service.save_file(
                unit,
                storage,
                organization_id=uuid.UUID(org),
                project_id=uuid.UUID(project_id),
                source_id=None,
                filename="big.txt",
                content_type="text/plain",
                data=data,
                created_by=uuid.UUID(created_by),
            )
    assert storage.puts == []
    assert storage.deletes == []


async def test_rejects_disallowed_extension_before_any_write(
    api, owner: TestUser, org: str, storage, unit_factory
) -> None:
    project_id = await new_project(api, owner, org)
    created_by = await _app_user_id(api, owner)

    with pytest.raises(ValidationError):
        async with await unit_factory() as unit:
            await file_service.save_file(
                unit,
                storage,
                organization_id=uuid.UUID(org),
                project_id=uuid.UUID(project_id),
                source_id=None,
                filename="payload.exe",
                content_type="application/octet-stream",
                data=b"MZ\x90\x00",
                created_by=uuid.UUID(created_by),
            )
    assert storage.puts == []


async def test_rejects_magic_byte_mismatch_before_any_write(
    api, owner: TestUser, org: str, storage, unit_factory
) -> None:
    project_id = await new_project(api, owner, org)
    created_by = await _app_user_id(api, owner)

    with pytest.raises(ValidationError):
        async with await unit_factory() as unit:
            await file_service.save_file(
                unit,
                storage,
                organization_id=uuid.UUID(org),
                project_id=uuid.UUID(project_id),
                source_id=None,
                filename="disguised.pdf",
                content_type="application/pdf",
                data=b"not actually a pdf",
                created_by=uuid.UUID(created_by),
            )
    assert storage.puts == []


async def test_signed_url_comes_from_the_storage_port(
    api, owner: TestUser, org: str, storage, unit_factory
) -> None:
    project_id = await new_project(api, owner, org)
    created_by = await _app_user_id(api, owner)

    async with await unit_factory() as unit:
        source_file = await file_service.save_file(
            unit,
            storage,
            organization_id=uuid.UUID(org),
            project_id=uuid.UUID(project_id),
            source_id=None,
            filename="notes.md",
            content_type="text/markdown",
            data=b"# competitor notes",
            created_by=uuid.UUID(created_by),
        )
        await unit.commit()

    url = await file_service.signed_url_for(storage, source_file)
    assert url == f"signed://{storage.bucket}/{source_file.object_key}"
    assert storage.sign_calls == [(storage.bucket, source_file.object_key)]
