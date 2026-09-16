"""Runtime configuration for the platform module.

Environment-driven, no framework dependencies. Values here are the
composition root's inputs; nothing in application/domain reads the
environment (plan §14.2).
"""

import os
import socket
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
            overrides it (plan §5.3); falls back to the Supavisor
            pooler (session mode) when the direct host does not resolve
            and SUPABASE_POOLER_HOST is configured.
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
        extraction_provider: LLM provider for structured extraction
            (Esperanto name). Empty = extraction disabled: extraction
            runs land failed/retryable rather than blocking enqueue
            (spec #47, ticket #49).
        extraction_model: Extraction model name.
        extraction_api_key: Optional provider key; empty = the
            provider's standard env var applies.
        chat_provider: LLM provider for the intelligence-chatbot router
            and composer (Esperanto name). Empty = chat tools report
            unavailability instead of failing conversations (spec #58,
            ticket #60).
        chat_model: Chat model name.
        chat_api_key: Optional provider key; empty = the provider's
            standard env var applies.
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
    extraction_provider: str = ""
    extraction_model: str = ""
    extraction_api_key: str = ""
    chat_provider: str = ""
    chat_model: str = ""
    chat_api_key: str = ""
    storage_bucket: str = "open-intel-files"
    seed_password: str = "seed-password-change-me"
    collection_daily_fetch_quota: int = 100
    maps_api_key: str = ""

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
            extraction_provider=environ.get("OPEN_INTEL_EXTRACTION_PROVIDER", ""),
            extraction_model=environ.get("OPEN_INTEL_EXTRACTION_MODEL", ""),
            extraction_api_key=environ.get("OPEN_INTEL_EXTRACTION_API_KEY", ""),
            chat_provider=environ.get("OPEN_INTEL_CHAT_PROVIDER", ""),
            chat_model=environ.get("OPEN_INTEL_CHAT_MODEL", ""),
            chat_api_key=environ.get("OPEN_INTEL_CHAT_API_KEY", ""),
            storage_bucket=environ.get("OPEN_INTEL_STORAGE_BUCKET", "open-intel-files"),
            seed_password=environ.get(
                "OPEN_INTEL_SEED_PASSWORD", "seed-password-change-me"
            ),
            collection_daily_fetch_quota=int(
                environ.get("OPEN_INTEL_COLLECTION_DAILY_FETCH_QUOTA", "100")
            ),
            maps_api_key=environ.get("OPEN_INTEL_MAPS_API_KEY", ""),
        )

    @property
    def database_dsn_asyncpg(self) -> str:
        """DSN usable by raw asyncpg (no SQLAlchemy dialect prefix)."""
        if self.database_dsn.startswith("postgresql+asyncpg://"):
            return "postgresql://" + self.database_dsn[len("postgresql+asyncpg://") :]
        return self.database_dsn


def _database_dsn(environ: Mapping[str, str]) -> str:
    """DSN for the managed project.

    Precedence: DATABASE_URL wins outright. Otherwise the direct
    ``db.<ref>.supabase.co`` host is used — unless SUPABASE_POOLER_HOST
    is configured and the direct host does not currently resolve.
    Supabase pulls the direct host's DNS record during failovers and
    maintenance; the pooler (Supavisor) keeps answering, so we fall
    back to it in session mode (default port 5432, user
    ``postgres.<ref>``), which asyncpg's prepared statements are safe
    against. The probe is one DNS lookup at settings load, so a
    recovered direct host is preferred again on the next process start.
    """
    if environ.get("DATABASE_URL"):
        return environ["DATABASE_URL"]
    host = environ.get("SUPABASE_DB_HOST", "")
    password = environ.get("SUPABASE_DB_PASSWORD", "")
    if not host or not password:
        return ""
    from urllib.parse import quote

    pooler_host = environ.get("SUPABASE_POOLER_HOST", "")
    if pooler_host and not _host_resolves(host):
        ref = environ.get("SUPABASE_PROJECT_REF", "") or _ref_from_db_host(host)
        user = f"postgres.{ref}" if ref else "postgres"
        port = environ.get("SUPABASE_POOLER_PORT", "5432")
        return (
            f"postgresql+asyncpg://{user}:{quote(password, safe='')}@"
            f"{pooler_host}:{port}/postgres"
        )
    return (
        f"postgresql+asyncpg://postgres:{quote(password, safe='')}@{host}:5432/postgres"
    )


def _ref_from_db_host(host: str) -> str:
    """Best-effort project ref from ``db.<ref>.supabase.co``."""
    parts = host.split(".")
    if len(parts) >= 3 and parts[0] == "db":
        return parts[1]
    return ""


def _host_resolves(host: str) -> bool:
    """One DNS probe. False on any resolution failure (NXDOMAIN, empty
    answer, resolver unreachable) — exactly the failure modes that make
    the direct connect host unusable."""
    try:
        socket.getaddrinfo(host, 5432)
    except OSError:
        return False
    return True
