"""Composition root for the Open Intel API.

Run locally (from the repository root):

    .venv/bin/uvicorn serve:app --reload --port 5055

This is the only place infrastructure concerns (environment settings,
filesystem module discovery) meet the FastAPI app factory.
"""

from pathlib import Path

from modules.platform.api.app import create_app
from modules.platform.infrastructure.discovery import discover_modules
from modules.platform.infrastructure.settings import Settings

app = create_app(
    config=Settings.from_env(),
    registry=discover_modules(Path(__file__).resolve().parent / "modules"),
)
