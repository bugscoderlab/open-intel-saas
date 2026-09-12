"""Organization and membership use cases (ticket #5).

Every mutation lands in the same transaction as its audit entry, and
organization creation additionally writes the OrganizationCreated outbox
event — the transactional-outbox pattern proven before any consumer
exists (ticket #8 decision).
"""

from uuid import UUID, uuid4

from modules.platform.application.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.application.unit_of_work import PlatformUnit
from modules.platform.domain.entities import (
    AuditEntry,
    Membership,
    Organization,
    OutboxEvent,
)
from modules.platform.domain.identity import Principal
from modules.platform.domain.permissions import Permission


async def create_organization(
    unit: PlatformUnit, principal: Principal, *, name: str
) -> Organization:
    """Create an Organization; the creator becomes its owner.

    Organization row + owner membership + audit entry + outbox event in
    one transaction.
    """
    organization = Organization(id=uuid4(), name=name, created_by=principal.app_user_id)
    await unit.organizations.create(organization)
    await unit.memberships.add(
        Membership(
            organization_id=organization.id,
            app_user_id=principal.app_user_id,
            role="owner",
        )
    )
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="organization.create",
            target_type="organization",
            target_id=str(organization.id),
            organization_id=organization.id,
            payload={"name": name},
        )
    )
    await unit.outbox.add(
        OutboxEvent(
            event_type="OrganizationCreated",
            payload={
                "organization_id": str(organization.id),
                "name": name,
                "created_by": str(principal.app_user_id),
            },
        )
    )
    return organization


async def get_organization(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
) -> Organization:
    await authz.require(principal, Permission.ORG_READ, organization_id=organization_id)
    organization = await unit.organizations.get(organization_id)
    if organization is None:
        raise NotFoundError("organization not found")
    return organization


async def list_organizations(
    unit: PlatformUnit,
    principal: Principal,
) -> list[Organization]:
    """Every Organization the principal is a member of."""
    return await unit.organizations.list_for_user(principal.app_user_id)


async def update_organization(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
    name: str,
) -> Organization:
    await authz.require(
        principal, Permission.ORG_UPDATE, organization_id=organization_id
    )
    organization = await unit.organizations.get(organization_id)
    if organization is None:
        raise NotFoundError("organization not found")
    updated = Organization(
        id=organization.id,
        name=name,
        created_by=organization.created_by,
    )
    await unit.organizations.update(updated)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="organization.update",
            target_type="organization",
            target_id=str(organization_id),
            organization_id=organization_id,
            payload={"name": name},
        )
    )
    return updated


async def delete_organization(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
) -> None:
    """Owner-only (matrix: org.delete). Cascade removes every tenant row."""
    await authz.require(
        principal, Permission.ORG_DELETE, organization_id=organization_id
    )
    if await unit.organizations.get(organization_id) is None:
        raise NotFoundError("organization not found")
    await unit.organizations.delete(organization_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="organization.delete",
            target_type="organization",
            target_id=str(organization_id),
            organization_id=organization_id,
            payload={},
        )
    )


async def list_members(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
) -> list[Membership]:
    await authz.require(
        principal, Permission.MEMBER_LIST, organization_id=organization_id
    )
    return await unit.memberships.list(organization_id)


async def change_member_role(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
    target_app_user_id: UUID,
    new_role: str,
) -> None:
    """Promote/demote a member (owners may touch admins/owners; admins,
    members only). The last owner cannot be demoted."""
    await authz.require(
        principal, Permission.MEMBER_CHANGE_ROLE, organization_id=organization_id
    )
    await authz.can_change_member_role(
        principal,
        organization_id=organization_id,
        target_app_user_id=target_app_user_id,
    )
    target = await unit.memberships.get(organization_id, target_app_user_id)
    if target is None:
        raise NotFoundError("member not found")
    if target.role == "owner" and new_role != "owner":
        owners = await unit.memberships.count_role(organization_id, "owner")
        if owners <= 1:
            raise ConflictError("cannot demote the last owner")
    await unit.memberships.update_role(organization_id, target_app_user_id, new_role)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="member.change_role",
            target_type="organization_member",
            target_id=str(target_app_user_id),
            organization_id=organization_id,
            payload={"role": new_role},
        )
    )


async def remove_member(
    unit: PlatformUnit,
    authz: AuthorizationService,
    principal: Principal,
    *,
    organization_id: UUID,
    target_app_user_id: UUID,
) -> None:
    """Remove a member; authorization fails immediately afterwards because
    the membership row is gone (revocation is real, not token-expiry based).
    The last owner cannot be removed."""
    await authz.require(
        principal, Permission.MEMBER_REMOVE, organization_id=organization_id
    )
    target = await unit.memberships.get(organization_id, target_app_user_id)
    if target is None:
        raise NotFoundError("member not found")
    if target.role == "owner":
        owners = await unit.memberships.count_role(organization_id, "owner")
        if owners <= 1:
            raise ConflictError("cannot remove the last owner")
    if target_app_user_id == principal.app_user_id:
        raise ForbiddenError("use organization delete to remove yourself")
    await unit.memberships.remove(organization_id, target_app_user_id)
    await unit.audit.record(
        AuditEntry(
            actor_id=principal.app_user_id,
            action="member.remove",
            target_type="organization_member",
            target_id=str(target_app_user_id),
            organization_id=organization_id,
            payload={},
        )
    )
