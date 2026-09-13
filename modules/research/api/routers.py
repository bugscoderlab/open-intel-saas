"""HTTP routers for the research module.

Routers stay thin: parse, call a service, map typed errors to statuses —
mirroring the platform boundary. All authorization decisions live in the
services behind the matrix; no role names here.
"""

from uuid import UUID

from fastapi import APIRouter

from modules.platform.api.deps import AuthzDep, PrincipalDep
from modules.platform.api.routers import endpoint
from modules.research.api.deps import ResearchUnitDep
from modules.research.api.schemas import (
    NotebookCreateRequest,
    NotebookResponse,
    NotebookUpdateRequest,
)
from modules.research.application.services import notebook_service
from modules.research.domain.entities import Notebook


def build_notebooks_router() -> APIRouter:
    router = APIRouter(tags=["notebooks"])

    @router.post(
        "/projects/{project_id}/notebooks",
        response_model=NotebookResponse,
        status_code=201,
    )
    @endpoint
    async def create_notebook(
        project_id: UUID,
        body: NotebookCreateRequest,
        unit: ResearchUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> NotebookResponse:
        notebook = await notebook_service.create_notebook(
            unit,
            authz,
            principal,
            project_id=project_id,
            name=body.name,
            description=body.description,
        )
        return _notebook_response(notebook)

    @router.get(
        "/projects/{project_id}/notebooks", response_model=list[NotebookResponse]
    )
    @endpoint
    async def list_notebooks(
        project_id: UUID, unit: ResearchUnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> list[NotebookResponse]:
        notebooks = await notebook_service.list_notebooks(
            unit, authz, principal, project_id=project_id
        )
        return [_notebook_response(n) for n in notebooks]

    @router.patch(
        "/projects/{project_id}/notebooks/{notebook_id}",
        response_model=NotebookResponse,
    )
    @endpoint
    async def update_notebook(
        project_id: UUID,
        notebook_id: UUID,
        body: NotebookUpdateRequest,
        unit: ResearchUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> NotebookResponse:
        notebook = await notebook_service.update_notebook(
            unit,
            authz,
            principal,
            project_id=project_id,
            notebook_id=notebook_id,
            name=body.name,
            description=body.description,
            archived=body.archived,
        )
        return _notebook_response(notebook)

    @router.delete("/projects/{project_id}/notebooks/{notebook_id}", status_code=204)
    @endpoint
    async def delete_notebook(
        project_id: UUID,
        notebook_id: UUID,
        unit: ResearchUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> None:
        await notebook_service.delete_notebook(
            unit, authz, principal, project_id=project_id, notebook_id=notebook_id
        )

    return router


def _notebook_response(notebook: Notebook) -> NotebookResponse:
    return NotebookResponse(
        id=notebook.id,
        organization_id=notebook.organization_id,
        project_id=notebook.project_id,
        name=notebook.name,
        description=notebook.description,
        archived=notebook.archived,
    )
