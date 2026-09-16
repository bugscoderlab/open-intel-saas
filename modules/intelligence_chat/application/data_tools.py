"""The three data tools (ticket #61, spec #58): research_search,
competitor_lookup, analytics. Each is a ChatTool built over a domain
port; the composition root (or a test) supplies the port, so
``intelligence_chat`` never imports another business module
(lint-imports independence).

Authorization note: the registry checks the tool's required_permission
BEFORE the handler runs, so the handlers trust the port layer — no
double gate.
"""

from uuid import UUID

from modules.intelligence_chat.application.tools import ChatTool
from modules.intelligence_chat.domain.entities import (
    Citation,
    ToolContext,
    ToolResult,
    ToolSpec,
)
from modules.intelligence_chat.domain.ports import (
    AnalyticsFunctionsPort,
    CompetitorProfilePort,
    ResearchSearchPort,
)

RESEARCH_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["query"],
    "additionalProperties": False,
}

COMPETITOR_LOOKUP_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string", "minLength": 1}},
    "required": ["name"],
    "additionalProperties": False,
}

ANALYTICS_SCHEMA = {
    "type": "object",
    "properties": {
        "metric": {"type": "string", "minLength": 1},
        "competitor_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "maxItems": 20,
        },
    },
    "required": ["metric"],
    "additionalProperties": False,
}

DEFAULT_TOP_K = 5


def build_research_search_tool(port: ResearchSearchPort) -> ChatTool:
    async def _handler(arguments: dict, context: ToolContext) -> ToolResult:
        query = arguments["query"].strip()
        top_k = min(arguments.get("top_k") or DEFAULT_TOP_K, 10)
        hits = await port.search(project_id=context.project_id, query=query, top_k=top_k)
        return ToolResult(
            tool="research_search",
            ok=True,
            payload={
                "hits": [
                    {
                        "source_id": str(hit.source_id),
                        "title": hit.title,
                        "excerpt": hit.excerpt,
                        "score": hit.score,
                    }
                    for hit in hits
                ]
            },
            citations=tuple(
                Citation(
                    origin="research_search",
                    ref={"source_id": str(hit.source_id), "excerpt": hit.excerpt},
                )
                for hit in hits
            ),
        )

    return ChatTool(
        spec=ToolSpec(
            name="research_search",
            description=(
                "Keyword search over the project's research sources;"
                " returns titled excerpts with source references."
            ),
            arguments_schema=RESEARCH_SEARCH_SCHEMA,
            required_permission="search.text",
        ),
        handler=_handler,
    )


def build_competitor_lookup_tool(port: CompetitorProfilePort) -> ChatTool:
    async def _handler(arguments: dict, context: ToolContext) -> ToolResult:
        name = arguments["name"].strip()
        profile = await port.profile(project_id=context.project_id, name=name)
        if profile is None:
            return ToolResult(
                tool="competitor_lookup",
                ok=False,
                error=f"no competitor named {name!r} in this project",
            )
        return ToolResult(
            tool="competitor_lookup",
            ok=True,
            payload={
                "competitor_id": str(profile.competitor_id),
                "name": profile.name,
                "locations": list(profile.locations),
                "services": [
                    {
                        "service_id": str(sp.service_id),
                        "service_name": sp.service_name,
                        "latest_price_amount": sp.latest_price_amount,
                        "latest_price_currency": sp.latest_price_currency,
                    }
                    for sp in profile.services
                ],
            },
            citations=(
                Citation(
                    origin="competitor_lookup",
                    ref={"competitor_id": str(profile.competitor_id)},
                ),
            ),
        )

    return ChatTool(
        spec=ToolSpec(
            name="competitor_lookup",
            description=(
                "Look up a competitor by name: locations and services"
                " with their latest approved prices."
            ),
            arguments_schema=COMPETITOR_LOOKUP_SCHEMA,
            required_permission="competitor.read",
        ),
        handler=_handler,
    )


def build_analytics_tool(port: AnalyticsFunctionsPort) -> ChatTool:
    async def _handler(arguments: dict, context: ToolContext) -> ToolResult:
        metric = arguments["metric"].strip()
        competitor_ids = arguments.get("competitor_ids")
        result = await port.run_metric(
            project_id=context.project_id,
            metric=metric,
            competitor_ids=tuple(UUID(cid) for cid in competitor_ids)
            if competitor_ids
            else None,
        )
        if result is None:
            return ToolResult(
                tool="analytics",
                ok=False,
                error=f"unknown metric {metric!r}",
            )
        return ToolResult(
            tool="analytics",
            ok=True,
            payload={
                "metric": result.metric,
                "unit": result.unit,
                "description": result.description,
                "points": list(result.points),
                "truncated": result.truncated,
            },
            citations=tuple(
                Citation(
                    origin="analytics",
                    ref={
                        "metric": result.metric,
                        **{
                            key: point[key]
                            for key in ("competitor_id", "service_id", "topic")
                            if key in point
                        },
                    },
                )
                for point in result.points
            ),
        )

    return ChatTool(
        spec=ToolSpec(
            name="analytics",
            description=(
                "Run an approved-data analytics metric (price_trend,"
                " competitor_comparison, service_coverage, review_topics,"
                " location_comparison) for this project."
            ),
            arguments_schema=ANALYTICS_SCHEMA,
            required_permission="analytics.read",
        ),
        handler=_handler,
    )
