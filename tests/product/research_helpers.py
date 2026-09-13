"""Shared scaffolding for the research-module HTTP-seam tests (tickets
#23/#24): the project/notebook/source factories. The matching ``org``
fixture (with outbox cleanup) lives in conftest.py — see
``research_org_cleanup`` for why the teardown sweeps outbox events.
"""

from __future__ import annotations

import uuid

from tests.product.conftest import TestUser, auth_headers

LONG_TEXT = (
    "The competitor offers full grooming services at escalating prices. "
    * 500
)  # well over 400 tokens under both tiktoken and the word-count fallback


async def new_project(api, owner: TestUser, org: str) -> str:
    response = await api.post(
        f"/organizations/{org}/projects",
        json={"name": f"Project {uuid.uuid4().hex[:8]}"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def new_notebook(api, owner: TestUser, project_id: str) -> str:
    response = await api.post(
        f"/projects/{project_id}/notebooks",
        json={"name": "Evidence"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def create_text_source(
    api, owner: TestUser, project_id: str, notebook_id: str, content: str
) -> dict:
    response = await api.post(
        f"/projects/{project_id}/sources",
        json={"notebook_id": notebook_id, "title": "Pricing page", "content": content},
        headers=auth_headers(owner),
    )
    assert response.status_code == 202, response.text
    return response.json()
