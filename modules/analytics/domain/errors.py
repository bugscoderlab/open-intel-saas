"""Typed analytics errors (spec #52)."""


class AnalyticsError(Exception):
    """Base for analytics failures."""


class AnalyticsQueryError(AnalyticsError):
    """The guarded read path failed (timeout, provider error) — a typed
    503/504 at the boundary, never a bare exception."""
