"""Response schemas for the analytics API (ticket #54)."""

from pydantic import BaseModel


class MetricResponse(BaseModel):
    metric: str
    unit: str
    description: str
    points: list[dict]
    truncated: bool
