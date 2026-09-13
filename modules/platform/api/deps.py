"""Request-scoped dependencies: unit of work, principal, authorization.

Identity comes only from the verified JWT — no endpoint accepts a
client-submitted Application user ID (plan §7.3, ticket #3).
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from modules.platform.application.errors import (
    NotAuthenticatedError,
    PlatformError,
    PrincipalResolutionError,
)
from modules.platform.application.identity import (
    IdentityProvider,
    TokenVerificationError,
)
from modules.platform.application.services.authorization import (
    AuthorizationService,
)
from modules.platform.application.unit_of_work import PlatformUnit
from modules.platform.domain.identity import Principal


async def get_unit(request: Request) -> AsyncIterator[PlatformUnit]:
    """One transaction per request: commit on success, rollback on error."""
    unit = request.app.state.unit_factory()
    async with unit:
        try:
            yield unit
        except PlatformError:
            await unit.rollback()
            raise
        await unit.commit()


async def get_principal(
    request: Request,
    unit: Annotated[PlatformUnit, Depends(get_unit)],
) -> Principal:
    provider: IdentityProvider = request.app.state.identity_provider
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        return await provider.verify_token(token.strip())
    except TokenVerificationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except PrincipalResolutionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def get_authz(
    unit: Annotated[PlatformUnit, Depends(get_unit)],
) -> AuthorizationService:
    return AuthorizationService(unit)


PrincipalDep = Annotated[Principal, Depends(get_principal)]
UnitDep = Annotated[PlatformUnit, Depends(get_unit)]
AuthzDep = Annotated[AuthorizationService, Depends(get_authz)]


def map_error(exc: PlatformError) -> HTTPException:
    """Service errors → HTTP statuses, in one place (no HTTPException in
    the application layer)."""
    from modules.platform.application.errors import (
        ConflictError,
        ForbiddenError,
        InvitationEmailMismatchError,
        InvitationInvalidError,
        NotFoundError,
        ServiceUnavailableError,
        ValidationError,
    )

    if isinstance(exc, (InvitationInvalidError,)):
        return HTTPException(status.HTTP_410_GONE, detail=str(exc))
    if isinstance(exc, (NotFoundError,)):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (ForbiddenError, InvitationEmailMismatchError)):
        return HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, (ConflictError,)):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, (ValidationError,)):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, (ServiceUnavailableError,)):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


__all__ = [
    "NotAuthenticatedError",
    "get_unit",
    "get_principal",
    "get_authz",
    "map_error",
    "PrincipalDep",
    "UnitDep",
    "AuthzDep",
]
