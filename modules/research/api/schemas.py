"""Pydantic request/response models for the research API boundary."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotebookCreateRequest(BaseModel):
    name: str
    description: str | None = None


class NotebookUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    archived: bool | None = None


class NotebookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    description: str | None
    archived: bool
