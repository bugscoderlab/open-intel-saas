"""Fixtures for the product scaffold tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def modules_root(tmp_path: Path) -> Iterator[Path]:
    """A fake modules/ tree: platform (required) + two optional modules."""
    root = tmp_path / "modules"
    for name, required in (
        ("platform", True),
        ("research", False),
        ("analytics", False),
    ):
        module_dir = root / name
        module_dir.mkdir(parents=True)
        (module_dir / "module.toml").write_text(
            f'name = "{name}"\ntitle = "{name.title()} module"\nrequired = {str(required).lower()}\n'
        )
    yield root


# ---------------------------------------------------------------------------
# Managed-project HTTP seam (tickets #3–#9): real app, real Supabase project,
# real JWTs. Users are created through the GoTrue admin API (the same
# provisioning path as every signup), used, and deleted again.
# ---------------------------------------------------------------------------

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

from modules.platform.infrastructure.db import create_engine
from modules.platform.infrastructure.email import RecordingEmailProvider
from modules.platform.infrastructure.identity import SupabaseIdentityProvider
from modules.platform.infrastructure.settings import Settings
from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit

TEST_EMAIL_DOMAIN = "http-test.open-intel.dev"


def unique_test_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@{TEST_EMAIL_DOMAIN}"


@dataclass
class TestUser:
    """A confirmed Application user with a live access token."""

    __test__ = False  # tell pytest this is a fixture, not a test class

    email: str
    password: str
    auth_user_id: str
    access_token: str
    app_user_id: str | None = field(default=None)


class SupabaseAdmin:
    """Thin GoTrue admin client for test user lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _headers(self) -> dict:
        key = self._settings.supabase_service_role_key
        return {"apikey": key, "Authorization": f"Bearer {key}"}

    async def create_confirmed_user(
        self, http: httpx.AsyncClient, email: str, password: str
    ) -> str:
        response = await http.post(
            f"{self._settings.supabase_url}/auth/v1/admin/users",
            headers=self._headers(),
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
            },
        )
        assert response.status_code in (200, 201), response.text
        return response.json()["id"]

    async def access_token(
        self, http: httpx.AsyncClient, email: str, password: str
    ) -> str:
        response = await http.post(
            f"{self._settings.supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": self._settings.supabase_publishable_key},
            json={"email": email, "password": password},
        )
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    async def delete_user(self, http: httpx.AsyncClient, auth_user_id: str) -> None:
        response = await http.delete(
            f"{self._settings.supabase_url}/auth/v1/admin/users/{auth_user_id}",
            headers=self._headers(),
        )
        assert response.status_code in (200, 204), response.text


@pytest.fixture(scope="session")
def settings() -> Settings:
    result = Settings.from_env()
    if not result.database_dsn or not result.supabase_service_role_key:
        pytest.skip("managed Supabase project not configured")
    return result


@pytest_asyncio.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=30) as client:
        yield client


@pytest.fixture
def admin(settings: Settings) -> SupabaseAdmin:
    return SupabaseAdmin(settings)


@pytest_asyncio.fixture
async def user_factory(
    settings: Settings, http: httpx.AsyncClient, admin: SupabaseAdmin
) -> AsyncIterator:
    """Creates confirmed users with tokens; deletes them at teardown."""
    created: list[TestUser] = []

    async def create(prefix: str = "user") -> TestUser:
        email = unique_test_email(prefix)
        password = f"pw-{uuid.uuid4().hex[:20]}"
        auth_user_id = await admin.create_confirmed_user(http, email, password)
        token = await admin.access_token(http, email, password)
        user = TestUser(
            email=email,
            password=password,
            auth_user_id=auth_user_id,
            access_token=token,
        )
        created.append(user)
        return user

    yield create

    for user in created:
        try:
            await admin.delete_user(http, user.auth_user_id)
        except AssertionError:
            pass  # already gone (test deleted it)


@pytest.fixture(scope="session")
def engine(settings: Settings):
    return create_engine(settings.database_dsn)


@pytest_asyncio.fixture
async def app_client(
    settings: Settings,
    engine,
):
    """The real application over the managed project, with a recording
    email provider so tests can assert invitation delivery."""
    from fastapi.testclient import TestClient

    from modules.platform.api.app import create_app
    from modules.platform.infrastructure.discovery import discover_modules
    from modules.research.api.routers import build_research_router
    from modules.research.infrastructure.unit_of_work import SqlResearchUnit

    repo_root = Path(__file__).resolve().parents[2]
    recording_email = RecordingEmailProvider()
    app = create_app(
        config=settings,
        registry=discover_modules(repo_root / "modules"),
        engine=engine,
        identity_provider=SupabaseIdentityProvider(
            supabase_url=settings.supabase_url, engine=engine
        ),
        email_provider=recording_email,
        unit_factory=lambda: SqlPlatformUnit(engine),
        invitation_base_url="http://shell.test",
        research_router=build_research_router(),
        research_unit_factory=lambda: SqlResearchUnit(engine),
    )
    app.state.recording_email = recording_email
    from tests.product.fakes import DeterministicEmbedder, RecordingFileStorage

    app.state.research_embedder = DeterministicEmbedder()
    # The storage seam (ticket #28): the recording fake stands in for
    # Supabase Storage — no real bucket in tests.
    app.state.research_storage = RecordingFileStorage()
    with TestClient(app, base_url="http://api.test") as client:
        yield client


@pytest_asyncio.fixture
async def api(settings: Settings):
    """Async single-loop client over the real app + managed project.

    Managed HTTP-seam tests are async end to end: one event loop drives
    the fixtures and the application, so connection pools never mix loops.
    """
    from httpx import ASGITransport, AsyncClient

    from modules.platform.api.app import create_app
    from modules.platform.infrastructure.discovery import discover_modules
    from modules.research.api.routers import build_research_router
    from modules.research.infrastructure.unit_of_work import SqlResearchUnit

    repo_root = Path(__file__).resolve().parents[2]
    engine = create_engine(settings.database_dsn)
    recording_email = RecordingEmailProvider()
    app = create_app(
        config=settings,
        registry=discover_modules(repo_root / "modules"),
        engine=engine,
        identity_provider=SupabaseIdentityProvider(
            supabase_url=settings.supabase_url, engine=engine
        ),
        email_provider=recording_email,
        unit_factory=lambda: SqlPlatformUnit(engine),
        invitation_base_url="http://shell.test",
        research_router=build_research_router(),
        research_unit_factory=lambda: SqlResearchUnit(engine),
    )
    app.state.recording_email = recording_email
    from tests.product.fakes import DeterministicEmbedder, RecordingFileStorage

    app.state.research_embedder = DeterministicEmbedder()
    app.state.research_storage = RecordingFileStorage()
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test")
    client.app = app  # type: ignore[attr-defined] # convenience handle for tests
    async with client:
        yield client
    await engine.dispose()


def auth_headers(user: TestUser) -> dict:
    return {"Authorization": f"Bearer {user.access_token}"}


@pytest_asyncio.fixture
async def org(api, owner: TestUser, settings) -> AsyncIterator[str]:
    """research_org_cleanup: an org for a test; teardown also sweeps
    outbox events (no FK from outbox_events to organizations, so org
    delete alone would litter the managed project). Shared by the
    research HTTP-seam tests; files that need a differently shaped org
    define their own local fixture, which shadows this one."""
    import asyncpg

    response = await api.post(
        "/organizations",
        json={"name": f"Org {uuid.uuid4().hex[:8]}"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    org_id = response.json()["id"]
    yield org_id
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "delete from public.outbox_events"
            " where payload->>'organization_id' = $1",
            org_id,
        )
        await conn.execute(
            "delete from public.organizations where id = $1::uuid", org_id
        )
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def drain_with(settings) -> AsyncIterator:
    """Run the in-process dispatcher with an explicitly chosen embedder —
    the composition seam (ticket #24): tests pick a deterministic fake,
    never a real provider."""
    from modules.platform.infrastructure.db import create_engine
    from modules.research.infrastructure.dispatcher import drain_pending_sources

    engine = create_engine(settings.database_dsn)

    async def _drain(embedder) -> int:
        return await drain_pending_sources(engine, embedder=embedder)

    yield _drain
    await engine.dispose()
