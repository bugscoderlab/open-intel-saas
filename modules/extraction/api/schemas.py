"""Request/response schemas for the extraction API (ticket #50)."""

from uuid import UUID

from pydantic import BaseModel


class ExtractionRunResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    snapshot_id: UUID
    status: str
    extraction_version: str
    error: str | None
