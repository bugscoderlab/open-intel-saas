"""Research domain entities (spec #21) — pure dataclasses (plan §14.2).

The Notebook is the research container (glossary), inherited from Open
Notebook: it lives inside a Project and will eventually hold Sources.
Like every tenant-owned row it carries organization_id + project_id so
tenant filtering is explicit and auditable on the row itself.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Notebook:
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    description: str | None
    archived: bool
    created_by: UUID
