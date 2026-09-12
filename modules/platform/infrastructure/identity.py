"""Supabase identity adapter: JWT verification + Application user
resolution (plan §7.3, ticket #3).

Verification uses the project's asymmetric keys via its JWKS endpoint
(new Supabase projects); a legacy HS256 secret is supported through
SUPABASE_AUTH_JWT_SECRET. The Application user is resolved through
``user_identities`` — never from anything the client submits.
"""

from typing import Any
from uuid import UUID

import httpx
import jwt
from jwt import PyJWK
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from modules.platform.domain.errors import (
    PrincipalResolutionError,
    TokenVerificationError,
)
from modules.platform.domain.identity import IdentityProvider, Principal
from modules.platform.infrastructure import db as tables
from modules.platform.infrastructure.db import create_session

PROVIDER_NAME = "supabase"


class SupabaseIdentityProvider(IdentityProvider):
    """Verifies Supabase Auth access tokens and resolves principals."""

    def __init__(
        self,
        *,
        supabase_url: str,
        engine: AsyncEngine,
        jwt_secret: str = "",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._supabase_url = supabase_url.rstrip("/")
        self._engine = engine
        self._jwt_secret = jwt_secret
        self._http = http or httpx.AsyncClient(timeout=10)
        self._jwks: dict[str, PyJWK] = {}
        self._jwks_fetched = False

    async def _get_signing_key(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if self._jwt_secret:
            return self._jwt_secret
        if not self._jwks_fetched:
            response = await self._http.get(
                f"{self._supabase_url}/auth/v1/.well-known/jwks.json"
            )
            response.raise_for_status()
            for key in response.json().get("keys", []):
                self._jwks[key["kid"]] = PyJWK(key)
            self._jwks_fetched = True
        if kid not in self._jwks:
            raise TokenVerificationError("unknown signing key")
        return self._jwks[kid].key

    async def verify_token(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            algorithms: list[str]
            if self._jwt_secret:
                algorithms = [header.get("alg", "HS256")]
            else:
                algorithms = [header.get("alg", "ES256")]
            key = await self._get_signing_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                options={"verify_aud": False},
            )
        except TokenVerificationError:
            raise
        except Exception as exc:
            raise TokenVerificationError(str(exc)) from exc

        subject = claims.get("sub")
        if not subject:
            raise TokenVerificationError("token has no subject")
        try:
            auth_user_id = UUID(subject)
        except ValueError as exc:
            raise TokenVerificationError("malformed subject") from exc

        app_user = await self._resolve_app_user(auth_user_id)
        if app_user is None:
            raise PrincipalResolutionError("no Application user for this identity")
        app_user_id, email, status = app_user
        token_email = claims.get("email", "") or ""
        return Principal(
            provider=PROVIDER_NAME,
            subject=subject,
            app_user_id=app_user_id,
            email=token_email or email,
            # Supabase access tokens do not reliably carry email_confirmed;
            # the product's own record is the source of truth: the
            # provisioning trigger flips status to active on confirmation.
            email_confirmed=status == "active",
        )

    async def _resolve_app_user(
        self, auth_user_id: UUID
    ) -> tuple[UUID, str, str] | None:
        """sub (auth user id) → Application user, through user_identities."""
        async with create_session(self._engine) as session:
            result = await session.execute(
                select(
                    tables.app_users.c.id,
                    tables.app_users.c.email,
                    tables.app_users.c.status,
                )
                .select_from(tables.user_identities)
                .join(
                    tables.app_users,
                    tables.app_users.c.id == tables.user_identities.c.app_user_id,
                )
                .where(tables.user_identities.c.auth_user_id == auth_user_id)
                .limit(1)
            )
            row = result.first()
            if row is None:
                return None
            return row.id, row.email, row.status
