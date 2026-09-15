"""FastAPI app factory for the Open Intel API.

The factory receives its settings and discovered module registry from
the composition root (``serve.py``) so this layer stays free of
environment access. Infrastructure pieces (engine, identity provider,
email provider) are constructed here unless injected — tests inject
fakes at exactly these seams.
"""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modules.platform.api.health import build_health_router
from modules.platform.api.routers import (
    build_invitations_router,
    build_me_router,
    build_organizations_router,
    build_projects_router,
    build_tags_router,
    build_teams_router,
)
from modules.platform.application.email import TransactionalEmailProvider
from modules.platform.application.identity import IdentityProvider
from modules.platform.application.registry import ModuleConfig, build_module_states
from modules.platform.domain.models import ModuleDefinition


def create_app(
    *,
    config: ModuleConfig,
    registry: list[ModuleDefinition],
    engine=None,
    identity_provider: IdentityProvider | None = None,
    email_provider: TransactionalEmailProvider | None = None,
    unit_factory=None,
    invitation_base_url: str = "http://localhost:3000",
    research_router: APIRouter | None = None,
    research_unit_factory=None,
    competitor_router: APIRouter | None = None,
    competitor_unit_factory=None,
    collection_router: APIRouter | None = None,
    collection_unit_factory=None,
    extraction_router: APIRouter | None = None,
    extraction_unit_factory=None,
    analytics_router: APIRouter | None = None,
    analytics_unit_factory=None,
) -> FastAPI:
    """Assemble the API. Fails to start if the platform module is absent.

    Infrastructure pieces arrive pre-constructed from the composition
    root (``serve.py``) or test fixtures — this layer never imports
    infrastructure (import-linter contract, plan §14.2).

    Optional-module routers arrive pre-built from the composition root
    and are mounted only while the module is enabled (plan §20) — the
    app factory itself never imports another module's code.
    """
    try:
        states = build_module_states(registry, config.disabled_modules)
    except ValueError as exc:
        raise RuntimeError(f"cannot start: {exc}") from exc

    if research_router is not None and research_unit_factory is None:
        raise RuntimeError(
            "cannot start: a research router was provided without a research unit factory"
        )
    if competitor_router is not None and competitor_unit_factory is None:
        raise RuntimeError(
            "cannot start: a competitor router was provided without a competitor unit factory"
        )
    if collection_router is not None and collection_unit_factory is None:
        raise RuntimeError(
            "cannot start: a collection router was provided without a collection unit factory"
        )
    if extraction_router is not None and extraction_unit_factory is None:
        raise RuntimeError(
            "cannot start: an extraction router was provided without an extraction unit factory"
        )
    if analytics_router is not None and analytics_unit_factory is None:
        raise RuntimeError(
            "cannot start: an analytics router was provided without an analytics unit factory"
        )

    app = FastAPI(title="Open Intel API")
    app.state.module_states = states
    app.state.engine = engine
    app.state.identity_provider = identity_provider
    app.state.email_provider = email_provider
    app.state.invitation_base_url = invitation_base_url
    app.state.unit_factory = unit_factory
    app.state.research_unit_factory = research_unit_factory
    app.state.competitor_unit_factory = competitor_unit_factory
    app.state.collection_unit_factory = collection_unit_factory
    app.state.extraction_unit_factory = extraction_unit_factory
    app.state.analytics_unit_factory = analytics_unit_factory

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_health_router(states))
    app.include_router(build_me_router())
    app.include_router(build_organizations_router())
    app.include_router(build_invitations_router())
    app.include_router(build_teams_router())
    app.include_router(build_projects_router())
    app.include_router(build_tags_router())

    if research_router is not None:
        research_state = next((s for s in states if s.name == "research"), None)
        if research_state is None or research_state.enabled:
            app.include_router(research_router)

    if competitor_router is not None:
        competitor_state = next(
            (s for s in states if s.name == "competitor_intelligence"), None
        )
        if competitor_state is None or competitor_state.enabled:
            app.include_router(competitor_router)

    if collection_router is not None:
        collection_state = next((s for s in states if s.name == "collection"), None)
        if collection_state is None or collection_state.enabled:
            app.include_router(collection_router)

    if extraction_router is not None:
        extraction_state = next((s for s in states if s.name == "extraction"), None)
        if extraction_state is None or extraction_state.enabled:
            app.include_router(extraction_router)

    if analytics_router is not None:
        analytics_state = next((s for s in states if s.name == "analytics"), None)
        if analytics_state is None or analytics_state.enabled:
            app.include_router(analytics_router)
    return app
