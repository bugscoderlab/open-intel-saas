"""Runtime configuration for the platform module.

Environment-driven, no framework dependencies. Values here are the
composition root's inputs; nothing in application/domain reads the
environment (plan §14.2).
"""

import os
from dataclasses import dataclass
from typing import Mapping

DISABLED_MODULES_ENV_VAR = "OPEN_INTEL_DISABLED_MODULES"


@dataclass(frozen=True)
class Settings:
    """Product-wide runtime settings.

    Attributes:
        disabled_modules: Module names to disable. The API must still
            start when an optional module is in this set (plan §20).
        database_dsn: Managed-Postgres DSN for SQLAlchemy/asyncpg. Built
            from the Supabase project host/password unless DATABASE_URL
            overrides it (plan §5.3).
        supabase_url: Project API URL — used for Auth (JWT verification
            JWKS, admin user provisioning in seeds/tests).
        supabase_service_role_key: Backend-only key. Never leaves
            infrastructure code (plan §8.2).
        supabase_publishable_key: Anonymous-key equivalent for Auth
            signup/token endpoints used by seeds/tests.
        jwt_secret: Optional HS256 verification secret. When unset, JWTs
            are verified against the project's JWKS (asymmetric keys).
        invitation_base_url: Public shell URL used to build accept links.
        resend_api_key: When set, invitation email goes through Resend;
            otherwise the console provider logs it (dev default).
        embedding_provider: Embedding provider for the research pipeline
            (Esperanto name, e.g. "openai"). Empty = embeddings disabled:
            sources land failed/retryable rather than blocking ingestion.
        embedding_model: Embedding model name (e.g. "text-embedding-3-small").
        embedding_api_key: Optional provider key; empty = the provider's
            standard env var applies (spec #21, ticket #24).
        seed_password: Password for users created by ``make seed``.
    """

    disabled_modules: frozenset[str] = frozenset()
    database_dsn: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_publishable_key: str = ""
    jwt_secret: str = ""
    invitation_base_url: str = "http://localhost:3000"
    resend_api_key: str = ""
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_api_key: str = ""
    seed_password: str = "seed-password-change-me"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        environ = os.environ if environ is None else environ
        raw = environ.get(DISABLED_MODULES_ENV_VAR, "")
        disabled = frozenset(item.strip() for item in raw.split(",") if item.strip())
        return cls(
            disabled_modules=disabled,
            database_dsn=_database_dsn(environ),
            supabase_url=environ.get("SUPABASE_URL", ""),
            supabase_service_role_key=environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            supabase_publishable_key=environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
            jwt_secret=environ.get("SUPABASE_AUTH_JWT_SECRET", ""),
            invitation_base_url=environ.get(
                "OPEN_INTEL_INVITATION_BASE_URL", "http://localhost:3000"
            ).rstrip("/"),
            resend_api_key=environ.get("RESEND_API_KEY", ""),
            embedding_provider=environ.get("OPEN_INTEL_EMBEDDING_PROVIDER", ""),
            embedding_model=environ.get("OPEN_INTEL_EMBEDDING_MODEL", ""),
            embedding_api_key=environ.get("OPEN_INTEL_EMBEDDING_API_KEY", ""),
            seed_password=environ.get(
                "OPEN_INTEL_SEED_PASSWORD", "seed-password-change-me"
            ),
        )

    @property
    def database_dsn_asyncpg(self) -> str:
        """DSN usable by raw asyncpg (no SQLAlchemy dialect prefix)."""
        if self.database_dsn.startswith("postgresql+asyncpg://"):
            return "postgresql://" + self.database_dsn[len("postgresql+asyncpg://") :]
        return self.database_dsn


def _database_dsn(environ: Mapping[str, str]) -> str:
    """DSN for the managed project; DATABASE_URL wins when present."""
    if environ.get("DATABASE_URL"):
        return environ["DATABASE_URL"]
    host = environ.get("SUPABASE_DB_HOST", "")
    password = environ.get("SUPABASE_DB_PASSWORD", "")
    if not host or not password:
        return ""
    from urllib.parse import quote

    return (
        f"postgresql+asyncpg://postgres:{quote(password, safe='')}@{host}:5432/postgres"
    )
