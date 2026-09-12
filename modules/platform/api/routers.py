"""HTTP routers for the platform module.

Routers stay thin: parse, call a service, map typed errors to statuses.
All authorization decisions live in the services behind the matrix —
no role names, no permission logic here (ticket #4 acceptance).
"""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Request

from modules.platform.api.deps import (
    AuthzDep,
    PrincipalDep,
    UnitDep,
    map_error,
)
from modules.platform.api.schemas import (
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InvitationPreviewResponse,
    InvitationResponse,
    MemberResponse,
    MemberRoleUpdateRequest,
    MeResponse,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
    ProjectCreateRequest,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectTagCreateRequest,
    ProjectTagResponse,
    ProjectTagUpdateRequest,
    ProjectUpdateRequest,
    TeamCreateRequest,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdateRequest,
)
from modules.platform.application.errors import PlatformError
from modules.platform.application.services import (
    invitation_service,
    organization_service,
    project_service,
    tag_service,
    team_service,
)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def endpoint(fn: F) -> F:
    """Translate service errors into HTTP responses (one place)."""

    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except PlatformError as exc:
            raise map_error(exc) from exc

    return wrapper  # type: ignore[return-value]


def build_me_router() -> APIRouter:
    router = APIRouter(tags=["me"])

    @router.get("/me", response_model=MeResponse)
    @endpoint
    async def me(principal: PrincipalDep) -> MeResponse:
        return MeResponse(
            app_user_id=principal.app_user_id,
            email=principal.email,
            email_confirmed=principal.email_confirmed,
        )

    return router


def build_organizations_router() -> APIRouter:
    router = APIRouter(tags=["organizations"])

    @router.post("/organizations", response_model=OrganizationResponse, status_code=201)
    @endpoint
    async def create_organization(
        body: OrganizationCreateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
    ) -> OrganizationResponse:
        organization = await organization_service.create_organization(
            unit, principal, name=body.name
        )
        return OrganizationResponse(id=organization.id, name=organization.name)

    @router.get("/organizations", response_model=list[OrganizationResponse])
    @endpoint
    async def list_organizations(
        unit: UnitDep, principal: PrincipalDep
    ) -> list[OrganizationResponse]:
        organizations = await organization_service.list_organizations(unit, principal)
        return [OrganizationResponse(id=o.id, name=o.name) for o in organizations]

    @router.get("/organizations/{organization_id}", response_model=OrganizationResponse)
    @endpoint
    async def get_organization(
        organization_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> OrganizationResponse:
        organization = await organization_service.get_organization(
            unit, authz, principal, organization_id=organization_id
        )
        return OrganizationResponse(id=organization.id, name=organization.name)

    @router.patch(
        "/organizations/{organization_id}", response_model=OrganizationResponse
    )
    @endpoint
    async def update_organization(
        organization_id: UUID,
        body: OrganizationUpdateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> OrganizationResponse:
        organization = await organization_service.update_organization(
            unit, authz, principal, organization_id=organization_id, name=body.name
        )
        return OrganizationResponse(id=organization.id, name=organization.name)

    @router.delete("/organizations/{organization_id}", status_code=204)
    @endpoint
    async def delete_organization(
        organization_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> None:
        await organization_service.delete_organization(
            unit, authz, principal, organization_id=organization_id
        )

    @router.get(
        "/organizations/{organization_id}/members", response_model=list[MemberResponse]
    )
    @endpoint
    async def list_members(
        organization_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> list[MemberResponse]:
        memberships = await organization_service.list_members(
            unit, authz, principal, organization_id=organization_id
        )
        emails = {}
        for membership in memberships:
            app_user = await unit.app_users.get_by_id(membership.app_user_id)
            emails[membership.app_user_id] = app_user.email if app_user else None
        return [
            MemberResponse(
                app_user_id=m.app_user_id, role=m.role, email=emails[m.app_user_id]
            )
            for m in memberships
        ]

    @router.patch(
        "/organizations/{organization_id}/members/{app_user_id}",
        response_model=MemberResponse,
    )
    @endpoint
    async def change_member_role(
        organization_id: UUID,
        app_user_id: UUID,
        body: MemberRoleUpdateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> MemberResponse:
        await organization_service.change_member_role(
            unit,
            authz,
            principal,
            organization_id=organization_id,
            target_app_user_id=app_user_id,
            new_role=body.role,
        )
        return MemberResponse(app_user_id=app_user_id, role=body.role)

    @router.delete(
        "/organizations/{organization_id}/members/{app_user_id}", status_code=204
    )
    @endpoint
    async def remove_member(
        organization_id: UUID,
        app_user_id: UUID,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> None:
        await organization_service.remove_member(
            unit,
            authz,
            principal,
            organization_id=organization_id,
            target_app_user_id=app_user_id,
        )

    return router


def build_invitations_router() -> APIRouter:
    router = APIRouter(tags=["invitations"])

    @router.post(
        "/organizations/{organization_id}/invitations",
        response_model=InvitationResponse,
        status_code=201,
    )
    @endpoint
    async def create_invitation(
        organization_id: UUID,
        body: InvitationCreateRequest,
        request: Request,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> InvitationResponse:
        created = await invitation_service.create_invitation(
            unit,
            authz,
            request.app.state.email_provider,
            principal,
            organization_id=organization_id,
            scope=body.scope,
            email=body.email,
            role=body.role,
            team_id=body.team_id,
            project_id=body.project_id,
            base_url=request.app.state.invitation_base_url,
        )
        invitation = created.invitation
        return InvitationResponse(
            id=invitation.id,
            organization_id=invitation.organization_id,
            scope=invitation.scope,
            team_id=invitation.team_id,
            project_id=invitation.project_id,
            email=invitation.email,
            role=invitation.role,
            expires_at=invitation.expires_at,
        )

    @router.get("/invitations/{token}", response_model=InvitationPreviewResponse)
    @endpoint
    async def preview_invitation(
        token: str, unit: UnitDep
    ) -> InvitationPreviewResponse:
        # No auth: possession of the single-use token is the capability.
        # The unit dependency only scopes the read; nothing here commits.
        invitation = await invitation_service.preview_invitation(unit, raw_token=token)
        organization = await unit.organizations.get(invitation.organization_id)
        return InvitationPreviewResponse(
            email=invitation.email,
            scope=invitation.scope,
            role=invitation.role,
            organization_name=organization.name if organization else "",
            expires_at=invitation.expires_at,
        )

    @router.post("/invitations/accept", status_code=204)
    @endpoint
    async def accept_invitation(
        body: InvitationAcceptRequest, unit: UnitDep, principal: PrincipalDep
    ) -> None:
        await invitation_service.accept_invitation(
            unit, principal, raw_token=body.token
        )

    return router


def build_teams_router() -> APIRouter:
    router = APIRouter(tags=["teams"])

    @router.post(
        "/organizations/{organization_id}/teams",
        response_model=TeamResponse,
        status_code=201,
    )
    @endpoint
    async def create_team(
        organization_id: UUID,
        body: TeamCreateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> TeamResponse:
        team = await team_service.create_team(
            unit, authz, principal, organization_id=organization_id, name=body.name
        )
        return TeamResponse(
            id=team.id, organization_id=team.organization_id, name=team.name
        )

    @router.get(
        "/organizations/{organization_id}/teams", response_model=list[TeamResponse]
    )
    @endpoint
    async def list_teams(
        organization_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> list[TeamResponse]:
        teams = await team_service.list_teams(
            unit, authz, principal, organization_id=organization_id
        )
        return [
            TeamResponse(id=t.id, organization_id=t.organization_id, name=t.name)
            for t in teams
        ]

    @router.get("/teams/{team_id}", response_model=TeamResponse)
    @endpoint
    async def get_team(
        team_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> TeamResponse:
        team = await team_service.get_team(unit, authz, principal, team_id=team_id)
        return TeamResponse(
            id=team.id, organization_id=team.organization_id, name=team.name
        )

    @router.patch("/teams/{team_id}", response_model=TeamResponse)
    @endpoint
    async def update_team(
        team_id: UUID,
        body: TeamUpdateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> TeamResponse:
        team = await team_service.update_team(
            unit, authz, principal, team_id=team_id, name=body.name
        )
        return TeamResponse(
            id=team.id, organization_id=team.organization_id, name=team.name
        )

    @router.delete("/teams/{team_id}", status_code=204)
    @endpoint
    async def delete_team(
        team_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> None:
        await team_service.delete_team(unit, authz, principal, team_id=team_id)

    @router.get("/teams/{team_id}/members", response_model=list[TeamMemberResponse])
    @endpoint
    async def list_team_members(
        team_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> list[TeamMemberResponse]:
        memberships = await team_service.list_team_members(
            unit, authz, principal, team_id=team_id
        )
        return [
            TeamMemberResponse(
                team_id=m.team_id, app_user_id=m.app_user_id, role=m.role
            )
            for m in memberships
        ]

    @router.delete("/teams/{team_id}/members/{app_user_id}", status_code=204)
    @endpoint
    async def remove_team_member(
        team_id: UUID,
        app_user_id: UUID,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> None:
        await team_service.remove_team_member(
            unit, authz, principal, team_id=team_id, target_app_user_id=app_user_id
        )

    return router


def build_projects_router() -> APIRouter:
    router = APIRouter(tags=["projects"])

    @router.post(
        "/organizations/{organization_id}/projects",
        response_model=ProjectResponse,
        status_code=201,
    )
    @endpoint
    async def create_project(
        organization_id: UUID,
        body: ProjectCreateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> ProjectResponse:
        project = await project_service.create_project(
            unit,
            authz,
            principal,
            organization_id=organization_id,
            name=body.name,
            owning_team_id=body.owning_team_id,
            visibility=body.visibility,
        )
        return _project_response(project)

    @router.get(
        "/organizations/{organization_id}/projects",
        response_model=list[ProjectResponse],
    )
    @endpoint
    async def list_projects(
        organization_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> list[ProjectResponse]:
        projects = await project_service.list_projects(
            unit, authz, principal, organization_id=organization_id
        )
        return [_project_response(p) for p in projects]

    @router.get("/projects/{project_id}", response_model=ProjectResponse)
    @endpoint
    async def get_project(
        project_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> ProjectResponse:
        project = await project_service.get_project(
            unit, authz, principal, project_id=project_id
        )
        return _project_response(project)

    @router.patch("/projects/{project_id}", response_model=ProjectResponse)
    @endpoint
    async def update_project(
        project_id: UUID,
        body: ProjectUpdateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> ProjectResponse:
        project = await project_service.update_project(
            unit,
            authz,
            principal,
            project_id=project_id,
            name=body.name,
            visibility=body.visibility,
        )
        return _project_response(project)

    @router.delete("/projects/{project_id}", status_code=204)
    @endpoint
    async def delete_project(
        project_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> None:
        await project_service.delete_project(
            unit, authz, principal, project_id=project_id
        )

    @router.get(
        "/projects/{project_id}/members", response_model=list[ProjectMemberResponse]
    )
    @endpoint
    async def list_project_members(
        project_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> list[ProjectMemberResponse]:
        memberships = await project_service.list_project_members(
            unit, authz, principal, project_id=project_id
        )
        return [
            ProjectMemberResponse(
                project_id=m.project_id, app_user_id=m.app_user_id, role=m.role
            )
            for m in memberships
        ]

    @router.delete("/projects/{project_id}/members/{app_user_id}", status_code=204)
    @endpoint
    async def remove_project_member(
        project_id: UUID,
        app_user_id: UUID,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> None:
        await project_service.remove_project_member(
            unit,
            authz,
            principal,
            project_id=project_id,
            target_app_user_id=app_user_id,
        )

    return router


def _project_response(project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        organization_id=project.organization_id,
        owning_team_id=project.owning_team_id,
        name=project.name,
        visibility=project.visibility,
    )


def build_tags_router() -> APIRouter:
    router = APIRouter(tags=["project-tags"])

    @router.post(
        "/projects/{project_id}/tags",
        response_model=ProjectTagResponse,
        status_code=201,
    )
    @endpoint
    async def create_tag(
        project_id: UUID,
        body: ProjectTagCreateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> ProjectTagResponse:
        tag = await tag_service.create_tag(
            unit,
            authz,
            principal,
            project_id=project_id,
            name=body.name,
            color=body.color,
        )
        return _tag_response(tag)

    @router.get("/projects/{project_id}/tags", response_model=list[ProjectTagResponse])
    @endpoint
    async def list_tags(
        project_id: UUID, unit: UnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> list[ProjectTagResponse]:
        tags = await tag_service.list_tags(
            unit, authz, principal, project_id=project_id
        )
        return [_tag_response(t) for t in tags]

    @router.patch(
        "/projects/{project_id}/tags/{tag_id}", response_model=ProjectTagResponse
    )
    @endpoint
    async def update_tag(
        project_id: UUID,
        tag_id: UUID,
        body: ProjectTagUpdateRequest,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> ProjectTagResponse:
        tag = await tag_service.update_tag(
            unit,
            authz,
            principal,
            project_id=project_id,
            tag_id=tag_id,
            name=body.name,
            color=body.color,
        )
        return _tag_response(tag)

    @router.delete("/projects/{project_id}/tags/{tag_id}", status_code=204)
    @endpoint
    async def delete_tag(
        project_id: UUID,
        tag_id: UUID,
        unit: UnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> None:
        await tag_service.delete_tag(
            unit, authz, principal, project_id=project_id, tag_id=tag_id
        )

    return router


def _tag_response(tag) -> ProjectTagResponse:
    return ProjectTagResponse(
        id=tag.id,
        organization_id=tag.organization_id,
        project_id=tag.project_id,
        name=tag.name,
        color=tag.color,
    )
