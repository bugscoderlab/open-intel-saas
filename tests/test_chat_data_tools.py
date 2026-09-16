"""Unit tests for the intelligence-chat data tools (ticket #61,
spec #58). Scripted fake ports — no database: the real adapters land
at the composition root (#63) and get exercised end-to-end there.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio


from modules.intelligence_chat.application.data_tools import (
    build_analytics_tool,
    build_competitor_lookup_tool,
    build_research_search_tool,
)
from modules.intelligence_chat.application.tools import Budget, ToolRegistry
from modules.intelligence_chat.domain.entities import (
    CompetitorProfile,
    MetricRun,
    PlanStep,
    ResearchHit,
    ServicePrice,
    ToolContext,
)

PROJECT = uuid4()


class FakeResearchSearchPort:
    def __init__(self, hits: tuple[ResearchHit, ...]) -> None:
        self.hits = hits
        self.calls: list[dict] = []

    async def search(self, *, project_id, query: str, top_k: int):
        assert project_id == PROJECT
        self.calls.append({"query": query, "top_k": top_k})
        return self.hits[:top_k]


class FakeCompetitorProfilePort:
    def __init__(self, found: CompetitorProfile | None) -> None:
        self._found = found
        self.names: list[str] = []

    async def profile(self, *, project_id, name: str):
        assert project_id == PROJECT
        self.names.append(name)
        return self._found


class FakeAnalyticsPort:
    def __init__(self, result: MetricRun | None) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def run_metric(self, *, project_id, metric, competitor_ids=None):
        assert project_id == PROJECT
        self.calls.append({"metric": metric, "competitor_ids": competitor_ids})
        return self.result


def _run(registry: ToolRegistry, tool: str, arguments: dict):
    return registry.execute(
        PlanStep(tool=tool, arguments=arguments),
        context=ToolContext(project_id=PROJECT),
        permissions=frozenset({"search.text", "competitor.read", "analytics.read"}),
        budget=Budget(),
    )


HITS = (
    ResearchHit(
        source_id=uuid4(),
        title="Grooming price list",
        excerpt="Full grooming RM88 at Paws",
        score=0.91,
    ),
    ResearchHit(
        source_id=uuid4(),
        title="Market scan",
        excerpt="Nail trims from RM25",
        score=0.82,
    ),
)


class TestResearchSearchTool:
    async def test_hits_carry_citation_refs(self):
        port = FakeResearchSearchPort(HITS)
        registry = ToolRegistry((build_research_search_tool(port),))
        result = await _run(registry, "research_search", {"query": "grooming"})
        assert result.ok
        assert len(result.payload["hits"]) == 2
        assert {c.ref["source_id"] for c in result.citations} == {
            str(h.source_id) for h in HITS
        }
        assert all(c.origin == "research_search" for c in result.citations)
        assert port.calls == [{"query": "grooming", "top_k": 5}]

    async def test_top_k_bounds_results_and_is_passed_through(self):
        port = FakeResearchSearchPort(HITS)
        registry = ToolRegistry((build_research_search_tool(port),))
        result = await _run(
            registry, "research_search", {"query": "grooming", "top_k": 1}
        )
        assert result.ok and len(result.payload["hits"]) == 1
        assert port.calls[0]["top_k"] == 1

    async def test_out_of_range_top_k_rejected_by_schema(self):
        port = FakeResearchSearchPort(HITS)
        registry = ToolRegistry((build_research_search_tool(port),))
        result = await _run(
            registry, "research_search", {"query": "grooming", "top_k": 99}
        )
        assert not result.ok and "invalid arguments" in result.error
        assert port.calls == []  # handler never ran


PROFILE = CompetitorProfile(
    competitor_id=uuid4(),
    name="Paws",
    locations=("Downtown",),
    services=(
        ServicePrice(
            service_id=uuid4(),
            service_name="Full grooming",
            latest_price_amount=str(Decimal("95.00")),
            latest_price_currency="MYR",
        ),
    ),
)


class TestCompetitorLookupTool:
    async def test_profile_payload_and_citation(self):
        port = FakeCompetitorProfilePort(PROFILE)
        registry = ToolRegistry((build_competitor_lookup_tool(port),))
        result = await _run(registry, "competitor_lookup", {"name": "Paws"})
        assert result.ok
        assert result.payload["name"] == "Paws"
        assert result.payload["locations"] == ["Downtown"]
        assert result.payload["services"][0]["latest_price_amount"] == "95.00"
        assert result.citations[0].ref == {"competitor_id": str(PROFILE.competitor_id)}
        assert port.names == ["Paws"]

    async def test_unknown_competitor_is_a_typed_rejection(self):
        port = FakeCompetitorProfilePort(None)
        registry = ToolRegistry((build_competitor_lookup_tool(port),))
        result = await _run(registry, "competitor_lookup", {"name": "Nope"})
        assert not result.ok and "no competitor named" in result.error


METRIC = MetricRun(
    metric="price_trend",
    unit="price",
    description="Approved prices per service over time.",
    points=(
        {
            "competitor_id": str(PROFILE.competitor_id),
            "service_id": str(PROFILE.services[0].service_id),
            "observed_on": "2026-09-01",
            "price_amount": "95.00",
            "price_currency": "MYR",
        },
    ),
    truncated=False,
)


class TestAnalyticsTool:
    async def test_metric_runs_with_point_citations(self):
        port = FakeAnalyticsPort(METRIC)
        registry = ToolRegistry((build_analytics_tool(port),))
        result = await _run(
            registry,
            "analytics",
            {"metric": "price_trend", "competitor_ids": [str(PROFILE.competitor_id)]},
        )
        assert result.ok
        assert result.payload["metric"] == "price_trend"
        assert len(result.payload["points"]) == 1
        assert port.calls == [
            {
                "metric": "price_trend",
                "competitor_ids": (PROFILE.competitor_id,),
            }
        ]
        assert result.citations[0].ref["metric"] == "price_trend"
        assert result.citations[0].ref["service_id"] == str(
            PROFILE.services[0].service_id
        )

    async def test_unknown_metric_is_a_typed_rejection(self):
        port = FakeAnalyticsPort(None)
        registry = ToolRegistry((build_analytics_tool(port),))
        result = await _run(registry, "analytics", {"metric": "haiku"})
        assert not result.ok and "unknown metric" in result.error
        # The port is the source of truth for unknown metrics — it ran
        # and reported None; the handler converted that to a rejection.
        assert port.calls == [{"metric": "haiku", "competitor_ids": None}]

    async def test_bad_competitor_id_shape_rejected_by_schema(self):
        port = FakeAnalyticsPort(METRIC)
        registry = ToolRegistry((build_analytics_tool(port),))
        result = await _run(
            registry, "analytics", {"metric": "price_trend", "competitor_ids": ["nope"]}
        )
        assert not result.ok and "invalid arguments" in result.error
        assert port.calls == []


class TestPermissionMapping:
    def test_tools_declare_matrix_permissions(self):
        registry = ToolRegistry(
            (
                build_research_search_tool(FakeResearchSearchPort(HITS)),
                build_competitor_lookup_tool(FakeCompetitorProfilePort(PROFILE)),
                build_analytics_tool(FakeAnalyticsPort(METRIC)),
            )
        )
        specs = {s.name: s for s in registry.allowlist_for(frozenset({"chat.use"}))}
        # chat.use alone grants nothing — every data tool needs its own.
        assert specs == {}
        viewer_specs = {
            s.name
            for s in registry.allowlist_for(
                frozenset(
                    {"chat.use", "search.text", "competitor.read", "analytics.read"}
                )
            )
        }
        assert viewer_specs == {"research_search", "competitor_lookup", "analytics"}
