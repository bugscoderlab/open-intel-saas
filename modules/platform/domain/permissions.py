"""Permission catalog, role matrix, and most-specific-scope-wins resolution
(ticket #4 decision, plan §8).

Route code references role names nowhere: the matrix below is the single
source of truth for what a Role grants, and the authorization service
answers "does this principal hold this Permission at this scope" by
resolving the most specific Role available and looking it up here.
"""


class Permission:
    """Internal ``resource.action`` strings (catalog grows per slice)."""

    # Organization
    ORG_READ = "org.read"
    ORG_UPDATE = "org.update"
    ORG_DELETE = "org.delete"
    MEMBER_LIST = "member.list"
    MEMBER_INVITE = "member.invite"
    MEMBER_REMOVE = "member.remove"
    MEMBER_CHANGE_ROLE = "member.change_role"
    TEAM_CREATE = "team.create"
    PROJECT_CREATE = "project.create"

    # Team
    TEAM_READ = "team.read"
    TEAM_UPDATE = "team.update"
    TEAM_DELETE = "team.delete"
    TEAM_MEMBER_INVITE = "team.member_invite"
    TEAM_MEMBER_REMOVE = "team.member_remove"

    # Project
    PROJECT_READ = "project.read"
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"
    PROJECT_MEMBER_INVITE = "project.member_invite"
    PROJECT_MEMBER_REMOVE = "project.member_remove"

    # Project tag
    TAG_CREATE = "tag.create"
    TAG_READ = "tag.read"
    TAG_UPDATE = "tag.update"
    TAG_DELETE = "tag.delete"

    # Notebook (research module, spec #21)
    NOTEBOOK_CREATE = "notebook.create"
    NOTEBOOK_READ = "notebook.read"
    NOTEBOOK_UPDATE = "notebook.update"
    NOTEBOOK_DELETE = "notebook.delete"

    # Source (research module, spec #21, ticket #23)
    SOURCE_CREATE = "source.create"
    SOURCE_READ = "source.read"
    SOURCE_RETRY = "source.retry"

    # Search (research module, spec #21, ticket #25)
    SEARCH_TEXT = "search.text"
    SEARCH_VECTOR = "search.vector"

    # Note (research module, spec #26, ticket #30)
    NOTE_CREATE = "note.create"
    NOTE_READ = "note.read"
    NOTE_UPDATE = "note.update"
    NOTE_DELETE = "note.delete"

    # Competitor intelligence (spec #31, ticket #33)
    COMPETITOR_CREATE = "competitor.create"
    COMPETITOR_READ = "competitor.read"
    COMPETITOR_UPDATE = "competitor.update"
    COMPETITOR_DELETE = "competitor.delete"
    LOCATION_CREATE = "location.create"
    LOCATION_READ = "location.read"
    LOCATION_UPDATE = "location.update"
    LOCATION_DELETE = "location.delete"
    SERVICE_CREATE = "service.create"
    SERVICE_READ = "service.read"
    SERVICE_DELETE = "service.delete"
    OBSERVATION_CREATE = "observation.create"
    OBSERVATION_READ = "observation.read"
    OBSERVATION_REVIEW = "observation.review"
    EVIDENCE_CREATE = "evidence.create"
    EVIDENCE_READ = "evidence.read"
    EVIDENCE_DELETE = "evidence.delete"
    SNAPSHOT_READ = "snapshot.read"
    COLLECTION_RUN = "collection.run"
    COLLECTION_JOB_MANAGE = "collection.job.manage"
    EXTRACTION_RUN = "extraction.run"


ALL_PERMISSIONS = frozenset(
    value for name, value in vars(Permission).items() if name.isupper()
)

TEAM_PERMISSIONS = frozenset(
    {
        Permission.TEAM_READ,
        Permission.TEAM_UPDATE,
        Permission.TEAM_DELETE,
        Permission.TEAM_MEMBER_INVITE,
        Permission.TEAM_MEMBER_REMOVE,
    }
)

PROJECT_PERMISSIONS = frozenset(
    {
        Permission.PROJECT_READ,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_DELETE,
        Permission.PROJECT_MEMBER_INVITE,
        Permission.PROJECT_MEMBER_REMOVE,
    }
)

TAG_PERMISSIONS = frozenset(
    {
        Permission.TAG_CREATE,
        Permission.TAG_READ,
        Permission.TAG_UPDATE,
        Permission.TAG_DELETE,
    }
)

NOTEBOOK_PERMISSIONS = frozenset(
    {
        Permission.NOTEBOOK_CREATE,
        Permission.NOTEBOOK_READ,
        Permission.NOTEBOOK_UPDATE,
        Permission.NOTEBOOK_DELETE,
    }
)

SOURCE_PERMISSIONS = frozenset(
    {
        Permission.SOURCE_CREATE,
        Permission.SOURCE_READ,
        Permission.SOURCE_RETRY,
    }
)

# Read-level roles search too (spec #21 user story 13).
SEARCH_PERMISSIONS = frozenset(
    {
        Permission.SEARCH_TEXT,
        Permission.SEARCH_VECTOR,
    }
)

NOTE_PERMISSIONS = frozenset(
    {
        Permission.NOTE_CREATE,
        Permission.NOTE_READ,
        Permission.NOTE_UPDATE,
        Permission.NOTE_DELETE,
    }
)

COMPETITOR_PERMISSIONS = frozenset(
    {
        Permission.COMPETITOR_CREATE,
        Permission.COMPETITOR_READ,
        Permission.COMPETITOR_UPDATE,
        Permission.COMPETITOR_DELETE,
    }
)

LOCATION_PERMISSIONS = frozenset(
    {
        Permission.LOCATION_CREATE,
        Permission.LOCATION_READ,
        Permission.LOCATION_UPDATE,
        Permission.LOCATION_DELETE,
    }
)

SERVICE_PERMISSIONS = frozenset(
    {
        Permission.SERVICE_CREATE,
        Permission.SERVICE_READ,
        Permission.SERVICE_DELETE,
    }
)

OBSERVATION_PERMISSIONS = frozenset(
    {
        Permission.OBSERVATION_CREATE,
        Permission.OBSERVATION_READ,
        Permission.OBSERVATION_REVIEW,
    }
)

EVIDENCE_PERMISSIONS = frozenset(
    {
        Permission.EVIDENCE_CREATE,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_DELETE,
    }
)

SNAPSHOT_PERMISSIONS = frozenset(
    {
        Permission.SNAPSHOT_READ,
    }
)

COLLECTION_PERMISSIONS = frozenset(
    {
        Permission.COLLECTION_RUN,
        Permission.COLLECTION_JOB_MANAGE,
    }
)

EXTRACTION_PERMISSIONS = frozenset(
    {
        Permission.EXTRACTION_RUN,
    }
)

ORG_BASE_PERMISSIONS = frozenset(
    {
        Permission.ORG_READ,
        Permission.ORG_UPDATE,
        Permission.MEMBER_LIST,
        Permission.MEMBER_INVITE,
        Permission.MEMBER_REMOVE,
        Permission.MEMBER_CHANGE_ROLE,
        Permission.TEAM_CREATE,
        Permission.PROJECT_CREATE,
    }
)


class Role:
    """Fixed, scope-scoped membership levels (never checked in route code)."""

    ORG_OWNER = "org:owner"
    ORG_ADMIN = "org:admin"
    ORG_MEMBER = "org:member"
    TEAM_MANAGER = "team:manager"
    TEAM_MEMBER = "team:member"
    PROJECT_EDITOR = "project:editor"
    PROJECT_VIEWER = "project:viewer"


# The matrix (ticket #4 acceptance, verbatim):
# - owner = everything admin gets, plus org.delete (member.change_role over
#   admins/owners is enforced by CAN_CHANGE_ROLE, below).
# - admin = all org permissions except delete/ownership, full access to all
#   org teams and projects (via the matrix, never a role-name check).
# - member = org.read, member.list, team.create, project.create only.
# - team manager = all team permissions plus implied editor on team
#   projects; team member = implied viewer on team projects.
# - project editor = all project, tag, and notebook permissions plus member
#   invite/remove; project viewer = project.read, tag.read, notebook.read.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.ORG_ADMIN: frozenset(
        ORG_BASE_PERMISSIONS
        | TEAM_PERMISSIONS
        | PROJECT_PERMISSIONS
        | TAG_PERMISSIONS
        | NOTEBOOK_PERMISSIONS
        | SOURCE_PERMISSIONS
        | SEARCH_PERMISSIONS
        | NOTE_PERMISSIONS
        | COMPETITOR_PERMISSIONS
        | LOCATION_PERMISSIONS
        | SERVICE_PERMISSIONS
        | OBSERVATION_PERMISSIONS
        | EVIDENCE_PERMISSIONS
        | SNAPSHOT_PERMISSIONS
        | COLLECTION_PERMISSIONS
        | EXTRACTION_PERMISSIONS
    ),
    Role.ORG_OWNER: frozenset(
        ORG_BASE_PERMISSIONS
        | TEAM_PERMISSIONS
        | PROJECT_PERMISSIONS
        | TAG_PERMISSIONS
        | NOTEBOOK_PERMISSIONS
        | SOURCE_PERMISSIONS
        | SEARCH_PERMISSIONS
        | NOTE_PERMISSIONS
        | COMPETITOR_PERMISSIONS
        | LOCATION_PERMISSIONS
        | SERVICE_PERMISSIONS
        | OBSERVATION_PERMISSIONS
        | EVIDENCE_PERMISSIONS
        | SNAPSHOT_PERMISSIONS
        | COLLECTION_PERMISSIONS
        | EXTRACTION_PERMISSIONS
        | {Permission.ORG_DELETE}
    ),
    Role.ORG_MEMBER: frozenset(
        {
            Permission.ORG_READ,
            Permission.MEMBER_LIST,
            Permission.TEAM_CREATE,
            Permission.PROJECT_CREATE,
        }
    ),
    Role.TEAM_MANAGER: frozenset(
        TEAM_PERMISSIONS
        | PROJECT_PERMISSIONS
        | TAG_PERMISSIONS
        | NOTEBOOK_PERMISSIONS
        | SOURCE_PERMISSIONS
        | SEARCH_PERMISSIONS
        | NOTE_PERMISSIONS
        | COMPETITOR_PERMISSIONS
        | LOCATION_PERMISSIONS
        | SERVICE_PERMISSIONS
        | OBSERVATION_PERMISSIONS
        | EVIDENCE_PERMISSIONS
        | SNAPSHOT_PERMISSIONS
        | COLLECTION_PERMISSIONS
        | EXTRACTION_PERMISSIONS
    ),
    Role.TEAM_MEMBER: frozenset(
        {
            Permission.TEAM_READ,
            Permission.PROJECT_READ,
            Permission.TAG_READ,
            Permission.NOTEBOOK_READ,
            Permission.SOURCE_READ,
            Permission.SEARCH_TEXT,
            Permission.SEARCH_VECTOR,
            Permission.NOTE_READ,
            Permission.COMPETITOR_READ,
            Permission.LOCATION_READ,
            Permission.SERVICE_READ,
            Permission.OBSERVATION_READ,
            Permission.EVIDENCE_READ,
            Permission.SNAPSHOT_READ,
        }
    ),
    Role.PROJECT_EDITOR: frozenset(
        PROJECT_PERMISSIONS
        | TAG_PERMISSIONS
        | NOTEBOOK_PERMISSIONS
        | SOURCE_PERMISSIONS
        | SEARCH_PERMISSIONS
        | NOTE_PERMISSIONS
        | COMPETITOR_PERMISSIONS
        | LOCATION_PERMISSIONS
        | SERVICE_PERMISSIONS
        | OBSERVATION_PERMISSIONS
        | EVIDENCE_PERMISSIONS
        | SNAPSHOT_PERMISSIONS
        | COLLECTION_PERMISSIONS
        | EXTRACTION_PERMISSIONS
    ),
    Role.PROJECT_VIEWER: frozenset(
        {
            Permission.PROJECT_READ,
            Permission.TAG_READ,
            Permission.NOTEBOOK_READ,
            Permission.SOURCE_READ,
            Permission.SEARCH_TEXT,
            Permission.SEARCH_VECTOR,
            Permission.NOTE_READ,
            Permission.COMPETITOR_READ,
            Permission.LOCATION_READ,
            Permission.SERVICE_READ,
            Permission.OBSERVATION_READ,
            Permission.EVIDENCE_READ,
            Permission.SNAPSHOT_READ,
        }
    ),
}

ORG_ROLES = frozenset({Role.ORG_OWNER, Role.ORG_ADMIN, Role.ORG_MEMBER})
TEAM_ROLES = frozenset({Role.TEAM_MANAGER, Role.TEAM_MEMBER})
PROJECT_ROLES = frozenset({Role.PROJECT_EDITOR, Role.PROJECT_VIEWER})

# Role names as stored in the membership tables (glossary: Role).
ORG_ROLE_NAMES = frozenset({"owner", "admin", "member"})
TEAM_ROLE_NAMES = frozenset({"manager", "member"})
PROJECT_ROLE_NAMES = frozenset({"editor", "viewer"})

# Matrix mapping from stored role name to matrix Role, per scope.
ORG_ROLE_MAP = {
    "owner": Role.ORG_OWNER,
    "admin": Role.ORG_ADMIN,
    "member": Role.ORG_MEMBER,
}
TEAM_ROLE_MAP = {
    "manager": Role.TEAM_MANAGER,
    "member": Role.TEAM_MEMBER,
}
PROJECT_ROLE_MAP = {
    "editor": Role.PROJECT_EDITOR,
    "viewer": Role.PROJECT_VIEWER,
}

# Changing the role OF an admin/owner is held by owners only (admins may
# change roles of plain members only).
_ROLE_RANK = {"member": 0, "admin": 1, "owner": 2}


def can_change_role(*, actor_org_role: str, target_org_role: str) -> bool:
    """member.change_role gate: admins act on members; owners on anyone."""
    if actor_org_role not in ("admin", "owner"):
        return False
    return _ROLE_RANK[target_org_role] == 0 or actor_org_role == "owner"


def resolve_role(
    *,
    org_role: str | None,
    team_role: str | None = None,
    project_role: str | None = None,
) -> str | None:
    """Most-specific-scope-wins: explicit project role → team-derived role
    → organization role. Returns the matrix Role, or None when the caller
    holds no membership anywhere in the chain."""
    if project_role is not None:
        return PROJECT_ROLE_MAP[project_role]
    if team_role is not None:
        return TEAM_ROLE_MAP[team_role]
    if org_role is not None:
        return ORG_ROLE_MAP[org_role]
    return None


def holds(role: str | None, permission: str) -> bool:
    """The matrix lookup: does this (resolved) Role grant the Permission?"""
    if role is None:
        return False
    return permission in ROLE_PERMISSIONS[role]
