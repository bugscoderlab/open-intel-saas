"""Search use cases (ticket #25, spec #21): keyword full-text and
semantic vector search inside a Project.

Authorization happens before retrieval: the service derives the tenant
scope from the project row, checks the matrix, and the scope is part of
the query predicate — ranking/similarity runs only within the tenant's
rows, never as a post-filter.
"""

from uuid import UUID

from modules.platform.application.errors import NotFoundError
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.domain.entities import Project
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission
from modules.research.application.errors import EmbeddingConfigurationError
from modules.research.application.processing import embed_chunks
from modules.research.domain.embedder import Embedder
from modules.research.domain.entities import SearchHit
from modules.research.domain.unit_of_work import ResearchUnit


async def _scoped_project(unit: ResearchUnit, project_id: UUID) -> Project:
    project = await unit.projects.get(project_id)
    if project is None:
        raise NotFoundError("project not found")
    return project


async def search_text(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    query: str,
    limit: int,
) -> list[SearchHit]:
    """search.text — tsvector over source title + full_text."""
    project = await _scoped_project(unit, project_id)
    await authz.require(
        principal,
        Permission.SEARCH_TEXT,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    query = query.strip()
    if not query:
        return []
    return await unit.search.search_text(
        project.organization_id, project_id, query=query, limit=limit
    )


async def search_vector(
    unit: ResearchUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    project_id: UUID,
    query: str,
    embedder: Embedder | None,
    limit: int,
) -> list[SearchHit]:
    """search.vector — embed the query, then pgvector cosine over the
    tenant's chunk rows. The query embedding uses the same embedder (and
    fake-injection seam) as the pipeline.

    A None embedder becomes a typed 503 here, inside the @endpoint error
    wrapper — raising it from the FastAPI dependency would escape as a
    bare 500."""
    if embedder is None:
        raise EmbeddingConfigurationError(
            "embedding provider/model not configured: set"
            " OPEN_INTEL_EMBEDDING_PROVIDER and OPEN_INTEL_EMBEDDING_MODEL"
        )
    project = await _scoped_project(unit, project_id)
    await authz.require(
        principal,
        Permission.SEARCH_VECTOR,
        organization_id=project.organization_id,
        team_id=project.owning_team_id,
        project_id=project_id,
    )
    query = query.strip()
    if not query:
        return []
    vectors = await embed_chunks(embedder, [query])
    return await unit.search.search_vector(
        project.organization_id,
        project_id,
        query_vector=vectors[0],
        limit=limit,
    )
