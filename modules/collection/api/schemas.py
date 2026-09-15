"""Pydantic request/response models for the collection API boundary.

Response models are the output allowlist (spec #41): exactly these
fields ever leave the API. The raw payload rides only on the single-
snapshot detail response — lists stay light.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CollectionRequest(BaseModel):
    connector_kind: Literal["website"] = "website"
    url: str = Field(min_length=1, max_length=2000)


class DiscoverRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    location: str = Field(min_length=1, max_length=500)


class CandidateResponse(BaseModel):
    """One discovered business — data only, never persisted (spec #41
    assumption 3)."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    address: str | None
    website: str | None
    provider_metadata: dict


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    connector_kind: str
    url: str
    status: str
    snapshot_id: UUID | None
    error: str | None
    requested_by: UUID


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    connector_kind: str
    url: str
    content_hash: str
    captured_at: datetime


class SnapshotDetailResponse(SnapshotResponse):
    raw_payload: str
