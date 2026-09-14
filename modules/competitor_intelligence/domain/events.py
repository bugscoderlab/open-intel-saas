"""Competitor-intelligence outbox event types (spec #31, plan §14.5).

Payloads are plain JSON dicts of string keys; every payload carries the
tenant scope (organization_id/project_id) so consumers never need to look
the competitor up to know which tenancy it belongs to.
"""

COMPETITOR_CHANGE_DETECTED = "CompetitorChangeDetected"
