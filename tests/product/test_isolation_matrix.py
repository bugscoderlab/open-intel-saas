"""The §17 tenant-isolation matrix (ticket #9), executable.

Every row is a named, independent test against the seeded two-tenant
fixture: Seed Org Alpha (seed-a1 owner, seed-a2 member) and Seed Org
Beta (seed-b1 owner, seed-b2 member). One failure pinpoints the leak.

Also the independent RLS safety net: the same queries, run as the
authenticated role with the user JWT in request.jwt.claims, still
cannot cross tenants even though the repository layer is bypassed.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.product.conftest import TestUser, auth_headers

SEED_PASSWORD_ENV = "OPEN_INTEL_SEED_PASSWORD"


@pytest.fixture(scope="module")
def seed_password() -> str:
    import os

    return os.environ.get(SEED_PASSWORD_ENV, "seed-password-change-me")


@pytest_asyncio.fixture(scope="module")
async def seeded(settings, seed_password) -> dict[str, TestUser]:
    """Live tokens for the four seeded users (one grant each per module)."""
    import httpx

    from tests.product.conftest import SupabaseAdmin

    admin = SupabaseAdmin(settings)
    emails = {
        "a1": "seed-a1@seed.open-intel.dev",
        "a2": "seed-a2@seed.open-intel.dev",
        "b1": "seed-b1@seed.open-intel.dev",
        "b2": "seed-b2@seed.open-intel.dev",
    }
    async with httpx.AsyncClient(timeout=30) as http:
        result = {}
        for key, email in emails.items():
            token = await admin.access_token(http, email, seed_password)
            result[key] = TestUser(
                email=email,
                password=seed_password,
                auth_user_id="",
                access_token=token,
            )
    return result


@pytest_asyncio.fixture(scope="module")
async def tenant_ids(settings) -> dict:
    """Organization/team/project/tag ids for both seed tenants."""
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        orgs = {
            row["name"]: str(row["id"])
            for row in await conn.fetch("select id, name from public.organizations")
        }
        teams = {
            row["name"]: str(row["id"])
            for row in await conn.fetch("select id, name from public.teams")
        }
        projects = {
            row["name"]: str(row["id"])
            for row in await conn.fetch("select id, name from public.projects")
        }
        tags = {
            row["name"]: str(row["id"])
            for row in await conn.fetch(
                "select t.id, t.name from public.project_tags t"
                " join public.projects p on p.id = t.project_id"
                " where p.organization_id = (select id from public.organizations"
                " where name = 'Seed Org Alpha')"
            )
        }
    finally:
        await conn.close()
    return {
        "A": {
            "org": orgs["Seed Org Alpha"],
            "team": teams["Alpha Team"],
            "project": projects["Alpha Project"],
            "tag": tags["competitors"],
        },
        "B": {
            "org": orgs["Seed Org Beta"],
            "project": projects["Beta Project"],
        },
    }


@pytest_asyncio.fixture(scope="module")
async def subjects(seeded, settings) -> dict[str, str]:
    """JWT sub (== Application user id) per seeded user."""
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        result = {}
        for key, user in seeded.items():
            result[key] = str(
                await conn.fetchval(
                    "select id from public.app_users where lower(email) = lower($1)",
                    user.email,
                )
            )
        return result
    finally:
        await conn.close()


# --- §17: no cross-tenant list/retrieve/edit/delete --------------------------


async def test_cross_tenant_organization_retrieve_denied(seeded, tenant_ids, api) -> None:
    for user_key, other in (("a1", "B"), ("b1", "A")):
        response = await api.get(
            f"/organizations/{tenant_ids[other]['org']}",
            headers=auth_headers(seeded[user_key]),
        )
        assert response.status_code == 404, f"{user_key} reached org {other}"


async def test_cross_tenant_team_retrieve_denied(seeded, tenant_ids, api) -> None:
    response = await api.get(
        f"/teams/{tenant_ids['A']['team']}", headers=auth_headers(seeded["b1"])
    )
    assert response.status_code == 404


async def test_cross_tenant_project_retrieve_denied(seeded, tenant_ids, api) -> None:
    for user_key, other in (("a1", "B"), ("b1", "A")):
        response = await api.get(
            f"/projects/{tenant_ids[other]['project']}",
            headers=auth_headers(seeded[user_key]),
        )
        assert response.status_code == 404


async def test_cross_tenant_project_tags_list_denied(seeded, tenant_ids, api) -> None:
    for user_key, other in (("a1", "B"), ("b1", "A")):
        response = await api.get(
            f"/projects/{tenant_ids[other]['project']}/tags",
            headers=auth_headers(seeded[user_key]),
        )
        assert response.status_code == 404


async def test_cross_tenant_organization_edit_denied(seeded, tenant_ids, api) -> None:
    response = await api.patch(
        f"/organizations/{tenant_ids['B']['org']}",
        json={"name": "Hijacked"},
        headers=auth_headers(seeded["a1"]),
    )
    assert response.status_code == 404
    # And the name really did not change.
    from_seed = await api.get(
        f"/organizations/{tenant_ids['B']['org']}",
        headers=auth_headers(seeded["b1"]),
    )
    assert from_seed.json()["name"] == "Seed Org Beta"


async def test_cross_tenant_project_edit_denied(seeded, tenant_ids, api) -> None:
    response = await api.patch(
        f"/projects/{tenant_ids['B']['project']}",
        json={"name": "Hijacked"},
        headers=auth_headers(seeded["a2"]),
    )
    assert response.status_code == 404


async def test_cross_tenant_tag_edit_denied(seeded, tenant_ids, api) -> None:
    response = await api.patch(
        f"/projects/{tenant_ids['A']['project']}/tags/{tenant_ids['A']['tag']}",
        json={"name": "hijacked"},
        headers=auth_headers(seeded["b1"]),
    )
    assert response.status_code in (403, 404)


async def test_cross_tenant_delete_denied(seeded, tenant_ids, api) -> None:
    response = await api.delete(
        f"/projects/{tenant_ids['B']['project']}",
        headers=auth_headers(seeded["a1"]),
    )
    assert response.status_code == 404
    # Beta's project still exists for Beta.
    assert (await api.get(
        f"/projects/{tenant_ids['B']['project']}",
        headers=auth_headers(seeded["b1"]),
    )).status_code == 200


async def test_member_list_of_other_org_is_denied(seeded, tenant_ids, api) -> None:
    response = await api.get(
        f"/organizations/{tenant_ids['B']['org']}/members",
        headers=auth_headers(seeded["a1"]),
    )
    assert response.status_code == 404


# --- §17: guessed IDs return nothing -----------------------------------------


async def test_guessed_organization_id_returns_nothing(seeded, api) -> None:
    import uuid as uuid_module

    response = await api.get(
        f"/organizations/{uuid_module.uuid4()}",
        headers=auth_headers(seeded["a1"]),
    )
    assert response.status_code == 404


async def test_guessed_invitation_token_is_indistinguishable(seeded, api) -> None:
    response = await api.get("/invitations/dGVzdHRva2Vu")
    assert response.status_code == 410


# --- §17: client-supplied tenant context cannot widen scope -------------------


async def test_client_supplied_organization_id_cannot_widen_scope(
    seeded, tenant_ids, api
) -> None:
    """Crafting a body with the *other* tenant's ids changes nothing."""
    response = await api.post(
        f"/projects/{tenant_ids['A']['project']}/tags",
        json={
            "name": "widening-attempt",
            "organization_id": tenant_ids["B"]["org"],
            "project_id": tenant_ids["B"]["project"],
        },
        headers=auth_headers(seeded["a1"]),
    )
    assert response.status_code == 201, response.text
    assert response.json()["organization_id"] == tenant_ids["A"]["org"]
    assert response.json()["project_id"] == tenant_ids["A"]["project"]
    # cleanup the probe tag
    await api.delete(
        f"/projects/{tenant_ids['A']['project']}/tags/{response.json()['id']}",
        headers=auth_headers(seeded["a1"]),
    )


# --- §17: viewer cannot mutate -----------------------------------------------


async def test_viewer_cannot_mutate_project_data(seeded, tenant_ids, api) -> None:
    """seed-a2 is a plain org member + team member: viewer on the team
    project. Every mutation is denied; reads work."""
    assert (await api.get(
        f"/projects/{tenant_ids['A']['project']}",
        headers=auth_headers(seeded["a2"]),
    )).status_code == 200
    assert (await api.patch(
        f"/projects/{tenant_ids['A']['project']}",
        json={"name": "nope"},
        headers=auth_headers(seeded["a2"]),
    )).status_code == 403
    assert (await api.post(
        f"/projects/{tenant_ids['A']['project']}/tags",
        json={"name": "nope"},
        headers=auth_headers(seeded["a2"]),
    )).status_code == 403


# --- §17: removal revokes immediately ----------------------------------------


async def test_removed_member_loses_access_immediately(seeded, tenant_ids, api) -> None:
    """Remove seed-a2 from Alpha, then watch every read fail at once."""
    members = (await api.get(
        f"/organizations/{tenant_ids['A']['org']}/members",
        headers=auth_headers(seeded["a1"]),
    )).json()
    a2_id = next(
        m["app_user_id"] for m in members if m["email"] == seeded["a2"].email
    )
    assert (await api.delete(
        f"/organizations/{tenant_ids['A']['org']}/members/{a2_id}",
        headers=auth_headers(seeded["a1"]),
    )).status_code == 204
    try:
        assert (await api.get(
            f"/organizations/{tenant_ids['A']['org']}",
            headers=auth_headers(seeded["a2"]),
        )).status_code == 404
        assert (await api.get(
            f"/projects/{tenant_ids['A']['project']}",
            headers=auth_headers(seeded["a2"]),
        )).status_code == 404
    finally:
        # Re-invite so the module fixture stays usable for later tests.
        await api.post(
            f"/organizations/{tenant_ids['A']['org']}/invitations",
            json={
                "email": seeded["a2"].email,
                "scope": "organization", "role": "member",
            },
            headers=auth_headers(seeded["a1"]),
        )
        token = api.app.state.recording_email.sent[-1]["accept_url"].rsplit(
            "token=", 1
        )[1]
        await api.post(
            "/invitations/accept", json={"token": token},
            headers=auth_headers(seeded["a2"]),
        )


# --- §17: service-role operations apply explicit tenant filters --------------


async def test_service_role_repository_reads_are_scope_filtered(
    seeded, tenant_ids, settings
) -> None:
    """The backend's service connection bypasses RLS; the repositories are
    the enforced layer. Querying Alpha's scope for Beta's tag returns
    nothing, and vice versa."""
    from modules.platform.infrastructure.db import create_engine
    from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit

    engine = create_engine(settings.database_dsn)
    try:
        async with SqlPlatformUnit(engine) as unit:
            alpha_scope = await unit.tags.get(
                UUID(tenant_ids["A"]["org"]),
                UUID(tenant_ids["A"]["project"]),
                UUID(tenant_ids["A"]["tag"]),
            )
            assert alpha_scope is not None
            cross = await unit.tags.get(
                UUID(tenant_ids["B"]["org"]),
                UUID(tenant_ids["B"]["project"]),
                UUID(tenant_ids["A"]["tag"]),
            )
            assert cross is None
            listed = await unit.tags.list_for_project(
                UUID(tenant_ids["B"]["org"]),
                UUID(tenant_ids["B"]["project"]),
            )
            assert all(
                str(t.organization_id) == tenant_ids["B"]["org"] for t in listed
            )
    finally:
        await engine.dispose()


# --- §17 (independent net): RLS policies keyed on the user JWT ----------------


async def test_rls_policies_block_cross_tenant_reads(
    seeded, tenant_ids, settings, subjects
) -> None:
    """Bypass the API and repositories entirely: as the authenticated role
    with the user JWT in request.jwt.claims, Supabase RLS must still deny
    cross-tenant rows (and allow own-tenant rows)."""
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        async with conn.transaction():
            await conn.execute("set local role authenticated")
            claims = json.dumps({"sub": subjects["a1"]})
            await conn.execute(
                "select set_config('request.jwt.claims', $1, true)", claims
            )

            # Own tenant visible.
            alpha_rows = await conn.fetch(
                "select name from public.project_tags order by name"
            )
            assert {r["name"] for r in alpha_rows} == {"competitors", "pricing"}

            # Cross-tenant organization invisible.
            beta = await conn.fetchrow(
                "select * from public.organizations where id = $1::uuid",
                tenant_ids["B"]["org"],
            )
            assert beta is None

            # Own organization visible.
            alpha = await conn.fetchrow(
                "select * from public.organizations where id = $1::uuid",
                tenant_ids["A"]["org"],
            )
            assert alpha is not None

            # Outbox is backend-only: RLS hides every row even from members.
            outbox = await conn.fetch("select * from public.outbox_events")
            assert outbox == []
        # transaction rolled back: role/claims never persist
    finally:
        await conn.close()


async def test_rls_policies_anon_role_sees_nothing(seeded, settings) -> None:
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        async with conn.transaction():
            await conn.execute("set local role anon")
            await conn.execute(
                "select set_config('request.jwt.claims', '{}', true)"
            )
            assert await conn.fetch("select * from public.project_tags") == []
            assert await conn.fetch("select * from public.organizations") == []
            assert await conn.fetch("select * from research.notebooks") == []
    finally:
        await conn.close()


# --- §17: research module — Notebook isolation (spec #21, ticket #22) --------


async def test_cross_tenant_notebook_list_denied(seeded, tenant_ids, api) -> None:
    """Alpha's notebook in Alpha's project: the other tenant cannot even
    list the project's notebooks (no membership → tenant-safe 404)."""
    created = await api.post(
        f"/projects/{tenant_ids['A']['project']}/notebooks",
        json={"name": "isolation-probe-list"},
        headers=auth_headers(seeded["a1"]),
    )
    assert created.status_code == 201, created.text
    for user_key in ("b1", "b2"):
        assert (await api.get(
            f"/projects/{tenant_ids['A']['project']}/notebooks",
            headers=auth_headers(seeded[user_key]),
        )).status_code == 404, f"{user_key} listed Alpha's notebooks"


async def test_cross_tenant_notebook_mutate_denied(seeded, tenant_ids, api) -> None:
    created = await api.post(
        f"/projects/{tenant_ids['A']['project']}/notebooks",
        json={"name": "isolation-probe-mutate"},
        headers=auth_headers(seeded["a1"]),
    )
    assert created.status_code == 201, created.text
    notebook_id = created.json()["id"]
    for user_key in ("b1", "b2"):
        assert (await api.patch(
            f"/projects/{tenant_ids['A']['project']}/notebooks/{notebook_id}",
            json={"name": "hijack"},
            headers=auth_headers(seeded[user_key]),
        )).status_code == 404
        assert (await api.delete(
            f"/projects/{tenant_ids['A']['project']}/notebooks/{notebook_id}",
            headers=auth_headers(seeded[user_key]),
        )).status_code == 404
    # A guessed notebook id is not an oracle: addressed inside the probing
    # tenant's own project URL space it still resolves to nothing.
    assert (await api.patch(
        f"/projects/{tenant_ids['B']['project']}/notebooks/{notebook_id}",
        json={"name": "hijack"},
        headers=auth_headers(seeded["b1"]),
    )).status_code == 404


async def test_service_role_notebook_reads_are_scope_filtered(
    seeded, tenant_ids, settings, api
) -> None:
    """The backend's service connection bypasses RLS; the research
    repository is the enforced layer: Alpha's notebook addressed with
    Beta's scope returns nothing."""
    from modules.platform.infrastructure.db import create_engine
    from modules.research.infrastructure.unit_of_work import SqlResearchUnit

    created = await api.post(
        f"/projects/{tenant_ids['A']['project']}/notebooks",
        json={"name": "isolation-probe-repo"},
        headers=auth_headers(seeded["a1"]),
    )
    assert created.status_code == 201, created.text
    notebook_id = created.json()["id"]

    engine = create_engine(settings.database_dsn)
    try:
        async with SqlResearchUnit(engine) as unit:
            alpha_scope = await unit.notebooks.get(
                UUID(tenant_ids["A"]["org"]),
                UUID(tenant_ids["A"]["project"]),
                UUID(notebook_id),
            )
            assert alpha_scope is not None
            cross = await unit.notebooks.get(
                UUID(tenant_ids["B"]["org"]),
                UUID(tenant_ids["B"]["project"]),
                UUID(notebook_id),
            )
            assert cross is None
            listed = await unit.notebooks.list_for_project(
                UUID(tenant_ids["B"]["org"]),
                UUID(tenant_ids["B"]["project"]),
            )
            assert all(
                str(n.organization_id) == tenant_ids["B"]["org"] for n in listed
            )
    finally:
        await engine.dispose()


async def test_rls_policies_block_cross_tenant_notebook_reads(
    seeded, tenant_ids, settings, subjects, api
) -> None:
    """Bypass the API and repositories entirely: as the authenticated role
    with the user JWT, RLS on research.notebooks must still deny
    cross-tenant rows (and allow own-tenant rows)."""
    created = await api.post(
        f"/projects/{tenant_ids['A']['project']}/notebooks",
        json={"name": "isolation-probe-rls"},
        headers=auth_headers(seeded["a1"]),
    )
    assert created.status_code == 201, created.text
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        async with conn.transaction():
            await conn.execute("set local role authenticated")
            claims = json.dumps({"sub": subjects["a1"]})
            await conn.execute(
                "select set_config('request.jwt.claims', $1, true)", claims
            )
            # Own-tenant row visible…
            rows = await conn.fetch("select organization_id from research.notebooks")
            org_ids = {str(r["organization_id"]) for r in rows}
            assert tenant_ids["A"]["org"] in org_ids
            # …and nothing from any other tenant.
            assert org_ids <= {tenant_ids["A"]["org"]}
            cross = await conn.fetch(
                "select * from research.notebooks where organization_id = $1::uuid",
                tenant_ids["B"]["org"],
            )
            assert cross == []
    finally:
        await conn.close()


# --- §17.5: research module — Source/chunk isolation (spec #21, #24) -------


async def _alpha_processed_source(seeded, tenant_ids, api, settings) -> str:
    """A chunked + embedded source in Alpha's project (processed by the
    real pipeline with the deterministic fake embedder — no provider)."""
    from modules.platform.infrastructure.db import create_engine
    from modules.research.infrastructure.dispatcher import drain_pending_sources
    from tests.product.fakes import DeterministicEmbedder

    notebook = await api.post(
        f"/projects/{tenant_ids['A']['project']}/notebooks",
        json={"name": "isolation-probe-source"},
        headers=auth_headers(seeded["a1"]),
    )
    assert notebook.status_code == 201, notebook.text
    created = await api.post(
        f"/projects/{tenant_ids['A']['project']}/sources",
        json={
            "notebook_id": notebook.json()["id"],
            "title": "isolation-probe-source",
            "content": "cross-tenant probe content " * 100,
        },
        headers=auth_headers(seeded["a1"]),
    )
    assert created.status_code == 202, created.text
    source_id = created.json()["id"]

    engine = create_engine(settings.database_dsn)
    try:
        processed = await drain_pending_sources(engine, embedder=DeterministicEmbedder())
        assert processed >= 1
    finally:
        await engine.dispose()
    return source_id


async def test_cross_tenant_source_and_chunk_reads_denied(
    seeded, tenant_ids, api, settings
) -> None:
    """Alpha's embedded chunks: the other tenant cannot read the job over
    the API, and the service-role repositories return nothing under a
    foreign tenant scope."""
    from modules.platform.infrastructure.db import create_engine
    from modules.research.infrastructure.unit_of_work import SqlResearchUnit

    source_id = await _alpha_processed_source(seeded, tenant_ids, api, settings)

    for user_key in ("b1", "b2"):
        assert (await api.get(
            f"/projects/{tenant_ids['A']['project']}/sources/{source_id}",
            headers=auth_headers(seeded[user_key]),
        )).status_code == 404, f"{user_key} read Alpha's source status"

    engine = create_engine(settings.database_dsn)
    try:
        async with SqlResearchUnit(engine) as unit:
            beta_scope_chunks = await unit.source_chunks.list_for_source(
                UUID(tenant_ids["B"]["org"]),
                UUID(tenant_ids["B"]["project"]),
                UUID(source_id),
            )
            assert beta_scope_chunks == []
            alpha_scope_chunks = await unit.source_chunks.list_for_source(
                UUID(tenant_ids["A"]["org"]),
                UUID(tenant_ids["A"]["project"]),
                UUID(source_id),
            )
            assert len(alpha_scope_chunks) >= 1
            assert all(c.embedding is not None for c in alpha_scope_chunks)
    finally:
        await engine.dispose()


async def test_rls_policies_block_cross_tenant_chunk_reads(
    seeded, tenant_ids, settings, subjects, api
) -> None:
    """Bypass the API and repositories entirely: as the authenticated role
    with the user JWT, RLS on research.source_chunks (with embeddings)
    must still deny cross-tenant rows."""
    source_id = await _alpha_processed_source(seeded, tenant_ids, api, settings)
    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        # Alpha's member sees own-tenant chunks only…
        async with conn.transaction():
            await conn.execute("set local role authenticated")
            await conn.execute(
                "select set_config('request.jwt.claims', $1, true)",
                json.dumps({"sub": subjects["a1"]}),
            )
            org_ids = {
                str(r["organization_id"])
                for r in await conn.fetch(
                    "select organization_id from research.source_chunks"
                )
            }
            assert tenant_ids["A"]["org"] in org_ids
            assert org_ids <= {tenant_ids["A"]["org"]}
        # …and Beta's member sees none of Alpha's chunks at all.
        async with conn.transaction():
            await conn.execute("set local role authenticated")
            await conn.execute(
                "select set_config('request.jwt.claims', $1, true)",
                json.dumps({"sub": subjects["b1"]}),
            )
            cross = await conn.fetch(
                "select * from research.source_chunks"
                " where organization_id = $1::uuid",
                tenant_ids["A"]["org"],
            )
            assert cross == []
            beta = await conn.fetch(
                "select * from public.outbox_events"
                " where payload->>'source_id' = $1",
                source_id,
            )
            assert beta == []
    finally:
        await conn.close()


# --- §17.5: research module — Search isolation (spec #21, ticket #25) ------


async def _tenant_processed_source(
    seeded, tenant_ids, api, settings, *, user_key, org_key, content, embedder
) -> str:
    """A processed source in the given tenant's project, embedded with the
    caller's fake so cross-tenant vector comparisons are meaningful."""
    from modules.platform.infrastructure.db import create_engine
    from modules.research.infrastructure.dispatcher import drain_pending_sources

    notebook = await api.post(
        f"/projects/{tenant_ids[org_key]['project']}/notebooks",
        json={"name": f"search-probe-{user_key}"},
        headers=auth_headers(seeded[user_key]),
    )
    assert notebook.status_code == 201, notebook.text
    created = await api.post(
        f"/projects/{tenant_ids[org_key]['project']}/sources",
        json={
            "notebook_id": notebook.json()["id"],
            "title": f"search-probe-{user_key}",
            "content": content,
        },
        headers=auth_headers(seeded[user_key]),
    )
    assert created.status_code == 202, created.text
    source_id = created.json()["id"]
    engine = create_engine(settings.database_dsn)
    try:
        assert (await drain_pending_sources(engine, embedder=embedder)) >= 1
    finally:
        await engine.dispose()
    return source_id


async def test_cross_tenant_search_denied(seeded, tenant_ids, api) -> None:
    """Probing tenant cannot address Alpha's project at all — the
    tenant-safe 404 covers both search endpoints."""
    for user_key in ("b1", "b2"):
        for endpoint in ("text", "vector"):
            assert (await api.get(
                f"/projects/{tenant_ids['A']['project']}/search/{endpoint}",
                params={"q": "grooming"},
                headers=auth_headers(seeded[user_key]),
            )).status_code == 404, f"{user_key} searched Alpha's project"


async def test_search_returns_no_cross_tenant_rows(seeded, tenant_ids, api, settings) -> None:
    """Alpha and Beta hold sources with the SAME keyword. Alpha's member
    searching Alpha's project must see only Alpha's source — in both
    text and vector search — even though Beta's chunk vectors are the
    closest possible match (same keyword space).

    The keyword is unique per run: the managed project keeps every
    probe source from earlier runs, and a shared fixed keyword gets
    crowded out of the top-N text hits once enough probes accumulate.
    The same accumulation breaks the vector side differently: every
    historical probe chunk is a 1-dim vector pointing the same way, so
    any new 1-dim query ties at cosine 1.0 and the top-N cut is
    arbitrary. Sweeping this test's own probe rows (search-probe-*) at
    the start keeps both sides deterministic without touching data
    owned by other tests."""
    from tests.product.fakes import KeywordEmbedder

    conn = await asyncpg.connect(settings.database_dsn_asyncpg, timeout=30)
    try:
        await conn.execute(
            "delete from research.source_chunks c using research.sources s"
            " where c.source_id = s.id and s.title like 'search-probe-%'"
            " and s.project_id in (select id from public.projects"
            " where name in ('Alpha Project', 'Beta Project'))"
        )
        await conn.execute(
            "delete from research.sources where title like 'search-probe-%'"
            " and project_id in (select id from public.projects"
            " where name in ('Alpha Project', 'Beta Project'))"
        )
        await conn.execute(
            "delete from research.notebooks where name like 'search-probe-%'"
            " and project_id in (select id from public.projects"
            " where name in ('Alpha Project', 'Beta Project'))"
        )
    finally:
        await conn.close()

    keyword = f"grooming{uuid4().hex[:10]}"
    embedder = KeywordEmbedder(keyword)
    content = f"{keyword} prices and full services. " * 100
    alpha_source = await _tenant_processed_source(
        seeded, tenant_ids, api, settings,
        user_key="a1", org_key="A", content=content, embedder=embedder,
    )
    beta_source = await _tenant_processed_source(
        seeded, tenant_ids, api, settings,
        user_key="b1", org_key="B", content=content, embedder=embedder,
    )
    # vector search embeds the query with the same fake as the chunks
    api.app.state.research_embedder = embedder

    text_hits = (await api.get(
        f"/projects/{tenant_ids['A']['project']}/search/text",
        params={"q": keyword},
        headers=auth_headers(seeded["a1"]),
    )).json()
    assert len(text_hits) >= 1
    # no probe litter remains after the sweep: Alpha's own source is the hit
    assert alpha_source in {h["source_id"] for h in text_hits}
    assert beta_source not in {h["source_id"] for h in text_hits}

    vector_hits = (await api.get(
        f"/projects/{tenant_ids['A']['project']}/search/vector",
        params={"q": keyword},
        headers=auth_headers(seeded["a1"]),
    )).json()
    assert len(vector_hits) >= 1
    assert alpha_source in {h["source_id"] for h in vector_hits}
    assert beta_source not in {h["source_id"] for h in vector_hits}

    # control: Beta's own member searching Beta's project sees Beta's copy
    beta_hits = (await api.get(
        f"/projects/{tenant_ids['B']['project']}/search/text",
        params={"q": keyword},
        headers=auth_headers(seeded["b1"]),
    )).json()
    assert beta_source in {h["source_id"] for h in beta_hits}
    assert alpha_source not in {h["source_id"] for h in beta_hits}
