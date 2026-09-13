"""HTTP routers for the research module.

Routers stay thin: parse, call a service, map typed errors to statuses —
mirroring the platform boundary. All authorization decisions live in the
services behind the matrix; no role names here.
"""

from uuid import UUID

from fastapi import APIRouter, Query

from modules.platform.api.deps import AuthzDep, PrincipalDep
from modules.platform.api.routers import endpoint
from modules.research.api.deps import ResearchUnitDep, SearchEmbedderDep
from modules.research.api.schemas import (
    NotebookCreateRequest,
    NotebookResponse,
    NotebookUpdateRequest,
    SearchHitResponse,
    SourceCreateRequest,
    SourceResponse,
)
from modules.research.application.services import (
    notebook_service,
    search_service,
    source_service,
)
from modules.research.domain.entities import Notebook, SearchHit, Source


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


def build_sources_router() -> APIRouter:
    """Text Source ingestion (ticket #23): create returns 202 with the
    source in "queued" — processing runs off-request via the outbox
    dispatcher (ADR-004); GET is the status poll; retry re-queues."""
    router = APIRouter(tags=["sources"])

    @router.post(
        "/projects/{project_id}/sources",
        response_model=SourceResponse,
        status_code=202,
    )
    @endpoint
    async def create_source(
        project_id: UUID,
        body: SourceCreateRequest,
        unit: ResearchUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> SourceResponse:
        source = await source_service.create_text_source(
            unit,
            authz,
            principal,
            project_id=project_id,
            notebook_id=body.notebook_id,
            title=body.title,
            content=body.content,
        )
        return _source_response(source)

    @router.get(
        "/projects/{project_id}/sources", response_model=list[SourceResponse]
    )
    @endpoint
    async def list_sources(
        project_id: UUID, unit: ResearchUnitDep, principal: PrincipalDep, authz: AuthzDep
    ) -> list[SourceResponse]:
        sources = await source_service.list_sources(
            unit, authz, principal, project_id=project_id
        )
        return [_source_response(s) for s in sources]

    @router.get(
        "/projects/{project_id}/sources/{source_id}",
        response_model=SourceResponse,
    )
    @endpoint
    async def get_source(
        project_id: UUID,
        source_id: UUID,
        unit: ResearchUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> SourceResponse:
        source = await source_service.get_source(
            unit,
            authz,
            principal,
            project_id=project_id,
            source_id=source_id,
        )
        return _source_response(source)

    @router.post(
        "/projects/{project_id}/sources/{source_id}/retry",
        response_model=SourceResponse,
        status_code=202,
    )
    @endpoint
    async def retry_source(
        project_id: UUID,
        source_id: UUID,
        unit: ResearchUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
    ) -> SourceResponse:
        source = await source_service.retry_source(
            unit,
            authz,
            principal,
            project_id=project_id,
            source_id=source_id,
        )
        return _source_response(source)

    return router


def build_search_router() -> APIRouter:
    """Tenant-scoped search (ticket #25): keyword full-text and semantic
    vector search inside a Project. Authorization before retrieval — the
    tenant scope is part of the query predicate, never a post-filter."""
    router = APIRouter(tags=["search"])

    @router.get(
        "/projects/{project_id}/search/text",
        response_model=list[SearchHitResponse],
    )
    @endpoint
    async def search_text(
        project_id: UUID,
        unit: ResearchUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
        q: str = "",
        limit: int = Query(default=10, ge=1, le=25),
    ) -> list[SearchHitResponse]:
        hits = await search_service.search_text(
            unit, authz, principal, project_id=project_id, query=q, limit=limit
        )
        return [_search_hit_response(h) for h in hits]

    @router.get(
        "/projects/{project_id}/search/vector",
        response_model=list[SearchHitResponse],
    )
    @endpoint
    async def search_vector(
        project_id: UUID,
        unit: ResearchUnitDep,
        principal: PrincipalDep,
        authz: AuthzDep,
        embedder: SearchEmbedderDep,
        q: str = "",
        limit: int = Query(default=10, ge=1, le=25),
    ) -> list[SearchHitResponse]:
        hits = await search_service.search_vector(
            unit,
            authz,
            principal,
            project_id=project_id,
            query=q,
            embedder=embedder,
            limit=limit,
        )
        return [_search_hit_response(h) for h in hits]

    return router


def build_research_router() -> APIRouter:
    """Everything the research module mounts: one router, wired by the
    composition root (serve.py) and the test seam (conftest)."""
    router = APIRouter()
    router.include_router(build_notebooks_router())
    router.include_router(build_sources_router())
    router.include_router(build_search_router())
    return router


def _source_response(source: Source) -> SourceResponse:
    return SourceResponse(
        id=source.id,
        organization_id=source.organization_id,
        project_id=source.project_id,
        notebook_id=source.notebook_id,
        title=source.title,
        type=source.type,
        status=source.status,
        error=source.error,
    )


def _search_hit_response(hit: SearchHit) -> SearchHitResponse:
    return SearchHitResponse(
        source_id=hit.source_id,
        title=hit.title,
        snippet=hit.snippet,
        score=hit.score,
    )
