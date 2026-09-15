"""The analytics unit of work: platform repositories only. Analytics has
no schema of its own (spec #52 assumption 1) — all data arrives through
the ApprovedFactsSource port; this unit exists to keep the module's
request seam identical to the other modules' (project load + authz in
one transaction)."""

from typing import Protocol

from modules.platform.domain.unit_of_work import PlatformUnit


class AnalyticsUnit(PlatformUnit, Protocol):
    """Platform repositories, nothing more (yet)."""
