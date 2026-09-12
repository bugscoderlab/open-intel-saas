"""Composition root for the Open Intel API.

Run locally (from the repository root):

    .venv/bin/uvicorn serve:app --reload --port 5055

This is the only place infrastructure concerns (environment settings,
filesystem module discovery) meet the FastAPI app factory.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from modules.platform.api.app import create_app  # noqa: E402
from modules.platform.infrastructure.db import create_engine  # noqa: E402
from modules.platform.infrastructure.discovery import discover_modules  # noqa: E402
from modules.platform.infrastructure.email import (  # noqa: E402
    ConsoleEmailProvider,
    ResendEmailProvider,
)
from modules.platform.infrastructure.identity import (  # noqa: E402
    SupabaseIdentityProvider,
)
from modules.platform.infrastructure.settings import Settings  # noqa: E402
from modules.platform.infrastructure.unit_of_work import SqlPlatformUnit  # noqa: E402

settings = Settings.from_env()

engine = create_engine(settings.database_dsn) if settings.database_dsn else None

app = create_app(
    config=settings,
    registry=discover_modules(Path(__file__).resolve().parent / "modules"),
    engine=engine,
    identity_provider=(
        SupabaseIdentityProvider(
            supabase_url=settings.supabase_url,
            engine=engine,
            jwt_secret=settings.jwt_secret,
        )
        if engine is not None and settings.supabase_url
        else None
    ),
    email_provider=(
        ResendEmailProvider(settings.resend_api_key)
        if settings.resend_api_key
        else ConsoleEmailProvider()
    ),
    unit_factory=(lambda: SqlPlatformUnit(engine)) if engine is not None else None,
    invitation_base_url=settings.invitation_base_url,
)
