"""Invitation use cases (ticket #6).

App-level invitations: no auth.users row is touched at invite time. Tokens
are hashed at rest, single-use, and expiring; the raw token exists only in
the emailed link, which routes through the shell's click page. Accepting
consumes the token and inserts the membership in one transaction, after
verifying the session's confirmed email equals the invited email.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from modules.platform.application.email import TransactionalEmailProvider
from modules.platform.application.errors import (
    ConflictError,
    InvitationEmailMismatchError,
    InvitationInvalidError,
    NotFoundError,
)
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.application.unit_of_work import PlatformUnit
from modules.platform.domain.entities import (
    AuditEntry,
    Invitation,
    Membership,
    ProjectMembership,
    TeamMembership,
)
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission

INVITATION_TTL = timedelta(days=7)
TOKEN_BYTES = 32

INVITATION_ROLES: dict[str, frozenset[str]] = {
    "organization": frozenset({"member"}),
    "team": frozenset({"member"}),
    "project": frozenset({"editor", "viewer"}),
}


@dataclass(frozen=True)
class CreatedInvitation:
    invitation: Invitation
    raw_token: str


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def create_invitation(
    unit: PlatformUnit,
    authz: AuthorizationService,
    email_provider: TransactionalEmailProvider,
    principal: Principal,
    *,
    organization_id: UUID,
    scope: str,
    email: str,
    role: str,
    team_id: UUID | None = None,
    project_id: UUID | None = None,
    base_url: str,
) -> CreatedInvitation:
    """Create an invitation and email the tokenized accept link.

    Permission per scope (matrix): organization → member.invite (lands as
    member); team → team.member_invite (lands as team member); project →
    project.member_invite (role chosen at invite time).
    """
    email = email.strip().lower()
    if scope not in INVITATION_ROLES:
        raise NotFoundError("unknown invitation scope")
    allowed_roles = INVITATION_ROLES[scope]
    if role not in allowed_roles:
        raise ConflictError(f"role must be one of {sorted(allowed_roles)}")

    if scope == "organization":
        await authz.require(
            principal, Permission.MEMBER_INVITE, organization_id=organization_id
        )
        team_id = None
        project_id = None
    elif scope == "team":
        if team_id is None:
            raise NotFoundError("team not found")
        team = await unit.teams.get(team_id)
        if team is None or team.organization_id != organization_id:
            raise NotFoundError("team not found")
        await authz.require(
            principal,
            Permission.TEAM_MEMBER_INVITE,
            organization_id=organization_id,
            team_id=team_id,
        )
        project_id = None
    else:
        if project_id is None:
            raise NotFoundError("project not found")
        project = await unit.projects.get(project_id)
        if project is None or project.organization_id != organization_id:
            raise NotFoundError("project not found")
        await authz.require(
            principal,
            Permission.PROJECT_MEMBER_INVITE,
            organization_id=organization_id,
            project_id=project_id,
        )
        team_id = None

    # Already a member of the target? Refuse instead of a dead invitation.
    invitee_id = await unit.app_users.get_id_by_email(email)
    if invitee_id is not None:
        already = False
        if scope == "organization":
            already = (
                await unit.memberships.get(organization_id, invitee_id) is not None
            )
        elif scope == "team":
            already = (
                await unit.team_memberships.get(team_id, invitee_id)  # type: ignore[arg-type]
                is not None
            )
        else:
            already = (
                await unit.project_memberships.get(project_id, invitee_id)  # type: ignore[arg-type]
                is not None
            )
        if already:
            raise ConflictError("this person is already a member")

    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    invitation = Invitation(
        id=uuid4(),
        organization_id=organization_id,
        scope=scope,
        team_id=team_id,
        project_id=project_id,
        email=email,
        role=role,
        token_hash=_hash_token(raw_token),
        invited_by=principal.app_user_id,
        expires_at=datetime.now(UTC) + INVITATION_TTL,
    )
    await unit.invitations.create(invitation)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="invitation.create",
            target_type="invitation",
            target_id=str(invitation.id),
            organization_id=organization_id,
            payload={
                "scope": scope,
                "email": email,
                "role": role,
                "team_id": str(team_id) if team_id else None,
                "project_id": str(project_id) if project_id else None,
            },
        )
    )
    organization = await unit.organizations.get(organization_id)
    organization_name = organization.name if organization else ""
    await email_provider.send_invitation(
        to_email=email,
        organization_name=organization_name,
        scope=scope,
        role=role,
        accept_url=f"{base_url}/invitations/accept?token={raw_token}",
    )
    return CreatedInvitation(invitation=invitation, raw_token=raw_token)


async def preview_invitation(unit: PlatformUnit, *, raw_token: str) -> Invitation:
    """What the accept click page shows: invited email, scope, expiry.

    No authentication: possession of the token is the capability. Expired
    or consumed tokens are indistinguishable from unknown ones.
    """
    invitation = await unit.invitations.get_by_token_hash(_hash_token(raw_token))
    if (
        invitation is None
        or invitation.consumed_at is not None
        or invitation.expires_at <= datetime.now(UTC)
    ):
        raise InvitationInvalidError("invitation link is invalid or expired")
    return invitation


async def accept_invitation(
    unit: PlatformUnit,
    principal: Principal,
    *,
    raw_token: str,
) -> Invitation:
    """Consume the token once and insert the membership atomically.

    The session's confirmed email must equal the invited email, so an
    email-change race cannot claim someone else's invitation.
    """
    invitation = await unit.invitations.get_by_token_hash(_hash_token(raw_token))
    if invitation is None:
        raise InvitationInvalidError("invitation link is invalid or expired")
    if invitation.consumed_at is not None or invitation.expires_at <= datetime.now(UTC):
        raise InvitationInvalidError("invitation link is invalid or expired")
    if (
        not principal.email_confirmed
        or principal.email.lower() != invitation.email.lower()
    ):
        raise InvitationEmailMismatchError(
            "session email does not match the invited email"
        )

    # Atomic single-use claim: exactly one concurrent accept wins.
    claimed = await unit.invitations.consume(invitation.id)
    if not claimed:
        raise InvitationInvalidError("invitation link is invalid or expired")

    if invitation.scope == "organization":
        await unit.memberships.add(
            Membership(
                organization_id=invitation.organization_id,
                app_user_id=principal.app_user_id,
                role=invitation.role,
            )
        )
    elif invitation.scope == "team":
        await unit.team_memberships.add(
            TeamMembership(
                team_id=invitation.team_id,  # type: ignore[arg-type]
                app_user_id=principal.app_user_id,
                role=invitation.role,
            )
        )
    else:
        await unit.project_memberships.add(
            ProjectMembership(
                project_id=invitation.project_id,  # type: ignore[arg-type]
                app_user_id=principal.app_user_id,
                role=invitation.role,
            )
        )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="invitation.accept",
            target_type="invitation",
            target_id=str(invitation.id),
            organization_id=invitation.organization_id,
            payload={"scope": invitation.scope, "email": principal.email},
        )
    )
    return invitation
