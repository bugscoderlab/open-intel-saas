"""Request/response schemas for the platform API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MeResponse(BaseModel):
    app_user_id: UUID
    email: str
    email_confirmed: bool


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class MemberResponse(BaseModel):
    app_user_id: UUID
    role: str
    email: str | None = None


class MemberRoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(owner|admin|member)$")


class InvitationCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    scope: str = Field(pattern="^(organization|team|project)$")
    role: str = Field(min_length=1, max_length=20)
    team_id: UUID | None = None
    project_id: UUID | None = None


class InvitationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    scope: str
    team_id: UUID | None
    project_id: UUID | None
    email: str
    role: str
    expires_at: datetime


class InvitationPreviewResponse(BaseModel):
    email: str
    scope: str
    role: str
    organization_name: str
    expires_at: datetime


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=16)


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TeamUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TeamResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str


class TeamMemberResponse(BaseModel):
    team_id: UUID
    app_user_id: UUID
    role: str


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    owning_team_id: UUID | None = None
    visibility: str = Field(default="private", pattern="^(private|team|organization)$")


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    visibility: str | None = Field(
        default=None, pattern="^(private|team|organization)$"
    )


class ProjectResponse(BaseModel):
    id: UUID
    organization_id: UUID
    owning_team_id: UUID | None
    name: str
    visibility: str


class ProjectMemberResponse(BaseModel):
    project_id: UUID
    app_user_id: UUID
    role: str


class ProjectTagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=30)


class ProjectTagUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=30)


class ProjectTagResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    color: str | None
