"""Pydantic request/response models for the competitor API boundary.

Response models are the output allowlist (spec #31): exactly these
fields ever leave the API for competitor-supplied content.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompetitorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    website: str | None = Field(default=None, max_length=2000)
    notes: str | None = None


class CompetitorUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    website: str | None = Field(default=None, max_length=2000)
    notes: str | None = None


class CompetitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    website: str | None
    notes: str | None


class LocationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    address: str | None = None


class LocationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    address: str | None = None


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    name: str
    address: str | None
