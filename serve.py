"""Composition root for the Open Intel API.

Run locally (from the repository root):

    .venv/bin/uvicorn serve:app --reload --port 5055

This is the only place infrastructure concerns (environment settings,
filesystem module discovery) meet the FastAPI app factory.
"""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from modules.analytics.api.routers import (  # noqa: E402
    build_analytics_router,
)
from modules.analytics.domain.entities import (  # noqa: E402
    DEFAULT_ROW_CAP,
    STATEMENT_TIMEOUT_SECONDS,
    ApprovedObservation,
    CatalogService,
    CompetitorLocation,
    Page,
)
from modules.analytics.infrastructure.unit_of_work import (  # noqa: E402
    SqlAnalyticsUnit,
)
from modules.collection.api.routers import (  # noqa: E402
    build_collection_router,
)
from modules.collection.infrastructure.dispatcher import (  # noqa: E402
    run_collection_dispatcher,
    run_collection_scheduler,
)
from modules.collection.infrastructure.google_places import (  # noqa: E402
    GooglePlacesMapsProvider,
)
from modules.collection.infrastructure.http_fetcher import (  # noqa: E402
    HttpxWebsiteFetcher,
)
from modules.collection.infrastructure.unit_of_work import (  # noqa: E402
    SqlCollectionUnit,
)
from modules.competitor_intelligence.api.routers import (  # noqa: E402
    build_competitor_router,
)
from modules.competitor_intelligence.infrastructure.unit_of_work import (  # noqa: E402
    SqlCompetitorUnit,
)
from modules.extraction.api.routers import (  # noqa: E402
    build_extraction_router,
)
from modules.extraction.domain.ports import (  # noqa: E402
    ProposedFact,
    SnapshotContent,
)
from modules.extraction.infrastructure.dispatcher import (  # noqa: E402
    run_extraction_dispatcher,
)
from modules.extraction.infrastructure.esperanto_extractor import (  # noqa: E402
    EsperantoExtractor,
)
from modules.extraction.infrastructure.unit_of_work import (  # noqa: E402
    SqlExtractionUnit,
)
from modules.platform.api.app import create_app  # noqa: E402
from modules.platform.infrastructure.db import create_engine  # noqa: E402
from modules.platform.infrastructure.discovery import discover_modules  # noqa: E402
from modules.platform.infrastructure.email import (  # noqa: E402
    ConsoleEmailProvider,
    ResendEmailProvider,
)
from modules.platform.infrastructure.identity import (  # noqa: E402
    SupabaseIdentityProvider,
)
from modules.platform.infrastructure.settings import Settings  # noqa: E402
from modules.platform.infrastructure.storage import SupabaseStorage  # noqa: E402
from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit  # noqa: E402
from modules.research.api.routers import build_research_router  # noqa: E402
from modules.research.infrastructure.dispatcher import run_dispatcher  # noqa: E402
from modules.research.infrastructure.embedder import EsperantoEmbedder  # noqa: E402
from modules.research.infrastructure.unit_of_work import SqlResearchUnit  # noqa: E402

settings = Settings.from_env()

engine = create_engine(settings.database_dsn) if settings.database_dsn else None

app = create_app(
    config=settings,
    registry=discover_modules(Path(__file__).resolve().parent / "modules"),
    engine=engine,
    identity_provider=(
        SupabaseIdentityProvider(
            supabase_url=settings.supabase_url,
            engine=engine,
            jwt_secret=settings.jwt_secret,
        )
        if engine is not None and settings.supabase_url
        else None
    ),
    email_provider=(
        ResendEmailProvider(settings.resend_api_key)
        if settings.resend_api_key
        else ConsoleEmailProvider()
    ),
    unit_factory=(lambda: SqlPlatformUnit(engine)) if engine is not None else None,
    invitation_base_url=settings.invitation_base_url,
    # The composition root is the only place module infrastructures meet:
    # the research router mounts only when the module state is enabled
    # (plan §20), decided inside the app factory.
    research_router=build_research_router() if engine is not None else None,
    research_unit_factory=(
        (lambda: SqlResearchUnit(engine)) if engine is not None else None
    ),
    competitor_router=build_competitor_router() if engine is not None else None,
    competitor_unit_factory=(
        (lambda: SqlCompetitorUnit(engine)) if engine is not None else None
    ),
    collection_router=build_collection_router() if engine is not None else None,
    collection_unit_factory=(
        (lambda: SqlCollectionUnit(engine)) if engine is not None else None
    ),
    extraction_router=build_extraction_router() if engine is not None else None,
    extraction_unit_factory=(
        (lambda: SqlExtractionUnit(engine)) if engine is not None else None
    ),
    analytics_router=build_analytics_router() if engine is not None else None,
    analytics_unit_factory=(
        (lambda: SqlAnalyticsUnit(engine)) if engine is not None else None
    ),
)

if engine is not None:
    dispatcher_engine = engine  # narrow for the closure (mypy)
    # Provider-agnostic embeddings (spec #21): Settings-driven, Esperanto
    # underneath. Unconfigured is fine at boot — the pipeline raises a
    # typed error per source, which lands failed and retryable.
    embedder = EsperantoEmbedder(
        provider=settings.embedding_provider,
        model_name=settings.embedding_model,
        api_key=settings.embedding_api_key or None,
    )
    app.state.research_embedder = embedder
    # Object storage (spec #26): Supabase Storage bound to the single
    # private bucket; absent when unconfigured — the file endpoints turn
    # that into a typed 503, mirroring the embedder seam.
    if settings.supabase_url and settings.supabase_service_role_key:
        app.state.research_storage = SupabaseStorage(
            supabase_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            bucket=settings.storage_bucket,
        )
    storage = getattr(app.state, "research_storage", None)
    # On-demand website collection (spec #41): the fetcher port's
    # reference adapter (plain httpx, SSRF-guarded) and the per-project
    # daily fetch quota enforced at enqueue time.
    app.state.collection_quota = settings.collection_daily_fetch_quota
    collection_fetcher = HttpxWebsiteFetcher()
    app.state.collection_fetcher = collection_fetcher
    # Maps discovery (spec #41): the MapsProvider port's reference
    # adapter, keyed from the environment. Unconfigured is fine at boot
    # — discover() raises the typed "not configured" error per call
    # (the embedder failure policy, ticket #24).
    app.state.collection_maps_provider = GooglePlacesMapsProvider(
        api_key=settings.maps_api_key
    )

    # Structured extraction (spec #47): the Extractor port's reference
    # adapter, Settings-driven; unconfigured deploys boot fine — the
    # drain marks each run failed with the typed configuration error.
    extraction_extractor = EsperantoExtractor(
        provider=settings.extraction_provider,
        model_name=settings.extraction_model,
        api_key=settings.extraction_api_key or None,
    )
    app.state.extraction_extractor = extraction_extractor

    # The SnapshotSource port, implemented here in the composition root
    # over the collection tables (plan §14.4: module infrastructures
    # meet only at the composition root).
    from sqlalchemy import select as _select

    class _CollectionSnapshotSource:
        async def get(self, snapshot_id) -> SnapshotContent | None:

            from modules.collection.infrastructure.db import (
                snapshots as _snapshots,
            )

            async with SqlCollectionUnit(engine) as unit:
                result = await unit._session.execute(  # noqa: SLF001
                    _select(_snapshots).where(_snapshots.c.id == snapshot_id)
                )
                row = result.first()
                if row is None:
                    return None
                return SnapshotContent(
                    snapshot_id=row.id,
                    project_id=row.project_id,
                    competitor_id=row.competitor_id,
                    url=row.url,
                    raw_payload=row.raw_payload,
                    captured_at=row.captured_at,
                )

    app.state.extraction_snapshot_source = _CollectionSnapshotSource()

    # The ObservationSink port, implemented here over the
    # competitor-intelligence unit: proposed facts land as PENDING
    # observations plus approved snapshot evidence links (ticket #50).
    class _CompetitorObservationSink:
        async def record_proposed(
            self,
            *,
            organization_id,
            project_id,
            competitor_id,
            snapshot_id,
            observed_on,
            extraction_version,
            facts: list[ProposedFact],
            recorded_by,
        ) -> int:
            from modules.competitor_intelligence.application.services.observation_service import (
                record_proposed_observations,
            )
            from modules.competitor_intelligence.domain.entities import (
                ProposedObservation,
            )
            from modules.competitor_intelligence.infrastructure.unit_of_work import (
                SqlCompetitorUnit,
            )

            async with SqlCompetitorUnit(engine) as unit:
                created = await record_proposed_observations(
                    unit,
                    project_id=project_id,
                    competitor_id=competitor_id,
                    snapshot_id=snapshot_id,
                    observed_on=observed_on,
                    extraction_version=extraction_version,
                    proposed=[
                        ProposedObservation(
                            kind=fact.kind,
                            confidence=fact.confidence,
                            price_amount=fact.price_amount,
                            price_currency=fact.price_currency,
                            excerpt=fact.excerpt,
                        )
                        for fact in facts
                    ],
                    recorded_by=recorded_by,
                )
                await unit.commit()
                return len(created)

    app.state.extraction_observation_sink = _CompetitorObservationSink()

    # Analytics (spec #52): the ApprovedFactsSource port, implemented
    # here over the competitor-intelligence tables. Read-only, guarded
    # (statement timeout + row cap with truncation flag) — dashboards
    # stay available when collectors/LLMs are down.
    class _CompetitorFactsSource:
        async def _query(self, stmt, *, limit: int):
            from sqlalchemy import text as _text

            async with SqlCompetitorUnit(engine) as unit:
                assert unit._session is not None
                await unit._session.execute(  # noqa: SLF001
                    # Constant integer — SET LOCAL takes no bind parameters.
                    _text(
                        f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_SECONDS * 1000}"
                    )
                )
                result = await unit._session.execute(stmt.limit(limit + 1))  # noqa: SLF001
                rows = result.all()
            return rows[:limit], len(rows) > limit

        async def approved_observations(
            self, *, project_id, competitor_id=None, kinds=None, limit=DEFAULT_ROW_CAP
        ) -> Page[ApprovedObservation]:
            from modules.competitor_intelligence.infrastructure.db import (
                observations as _observations,
            )

            stmt = _select(_observations).where(
                _observations.c.project_id == project_id,
                _observations.c.approval_state == "approved",
                _observations.c.superseded_by.is_(None),
            )
            if competitor_id is not None:
                stmt = stmt.where(_observations.c.competitor_id == competitor_id)
            if kinds is not None:
                stmt = stmt.where(_observations.c.kind.in_(kinds))
            rows, truncated = await self._query(
                stmt.order_by(_observations.c.observed_on), limit=limit
            )
            return Page(
                rows=tuple(
                    ApprovedObservation(
                        id=row.id,
                        competitor_id=row.competitor_id,
                        service_id=row.service_id,
                        location_id=row.location_id,
                        kind=row.kind,
                        price_amount=row.price_amount,
                        price_currency=row.price_currency,
                        observed_on=row.observed_on,
                        superseded_by=row.superseded_by,
                    )
                    for row in rows
                ),
                truncated=truncated,
            )

        async def services(self, *, project_id, limit=DEFAULT_ROW_CAP):
            from modules.competitor_intelligence.infrastructure.db import (
                services as _services,
            )

            stmt = _select(_services).where(_services.c.project_id == project_id)
            rows, truncated = await self._query(stmt, limit=limit)
            return Page(
                rows=tuple(
                    CatalogService(id=row.id, project_id=row.project_id, name=row.name)
                    for row in rows
                ),
                truncated=truncated,
            )

        async def locations(
            self, *, project_id, competitor_id=None, limit=DEFAULT_ROW_CAP
        ):
            from modules.competitor_intelligence.infrastructure.db import (
                locations as _locations,
            )

            stmt = _select(_locations).where(_locations.c.project_id == project_id)
            if competitor_id is not None:
                stmt = stmt.where(_locations.c.competitor_id == competitor_id)
            rows, truncated = await self._query(stmt, limit=limit)
            return Page(
                rows=tuple(
                    CompetitorLocation(
                        id=row.id,
                        project_id=row.project_id,
                        competitor_id=row.competitor_id,
                        name=row.name,
                    )
                    for row in rows
                ),
                truncated=truncated,
            )

    app.state.analytics_facts_source = _CompetitorFactsSource()

    @app.on_event("startup")
    async def _start_research_dispatcher() -> None:
        """Off-request source processing (ADR-004): the in-process
        dispatcher drains SourceSubmitted outbox events until shutdown.
        Tests drive the same drain function directly instead."""
        asyncio.create_task(
            run_dispatcher(dispatcher_engine, embedder=embedder, storage=storage)
        )
        # Off-request collection jobs (spec #41, same ADR-004 pattern):
        # POST enqueues; this loop fetches and snapshots until shutdown.
        asyncio.create_task(
            run_collection_dispatcher(dispatcher_engine, collection_fetcher)
        )
        # Scheduled collection (ticket #44): claims due schedules through
        # the outbox and runs them through the same pipeline.
        asyncio.create_task(
            run_collection_scheduler(dispatcher_engine, collection_fetcher)
        )
        # Structured extraction (ticket #50, ADR-004): drains
        # ExtractionRequested runs through the extractor and records
        # proposed observations through the sink.
        asyncio.create_task(
            run_extraction_dispatcher(
                dispatcher_engine,
                app.state.extraction_extractor,
                app.state.extraction_snapshot_source,
                app.state.extraction_observation_sink,
            )
        )
