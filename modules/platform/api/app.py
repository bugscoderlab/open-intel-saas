"""FastAPI app factory for the Open Intel API.

The factory receives its settings and discovered module registry from
the composition root (``serve.py``) so this layer stays free of
infrastructure imports.
"""

from fastapi import FastAPI

from modules.platform.api.health import build_health_router
from modules.platform.application.registry import ModuleConfig, build_module_states
from modules.platform.domain.models import ModuleDefinition


def create_app(
    *,
    config: ModuleConfig | None = None,
    registry: list[ModuleDefinition] | None = None,
) -> FastAPI:
    """Assemble the API. Fails to start if the platform module is absent."""
    if config is None or registry is None:
        raise TypeError("config and registry must be provided by the composition root")
    try:
        states = build_module_states(registry, config.disabled_modules)
    except ValueError as exc:
        raise RuntimeError(f"cannot start: {exc}") from exc
    app = FastAPI(title="Open Intel API")
    app.state.module_states = states
    app.include_router(build_health_router(states))
    return app
