"""Pydantic request/response models for the competitor API boundary.

Response models are the output allowlist (spec #31): exactly these
fields ever leave the API for competitor-supplied content.
"""

from datetime import date
from decimal import Decimal
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


class ServiceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str


class ObservationCreateRequest(BaseModel):
    service_id: UUID | None = None
    location_id: UUID | None = None
    kind: str = Field(default="price", max_length=50)
    price_amount: Decimal = Field(gt=0, decimal_places=2)
    price_currency: str = Field(min_length=3, max_length=3)
    observed_on: date


class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    competitor_id: UUID
    service_id: UUID | None
    location_id: UUID | None
    kind: str
    price_amount: Decimal | None
    price_currency: str | None
    observed_on: date
    confidence: Decimal
    extraction_version: str
    approval_state: str
    superseded_by: UUID | None
