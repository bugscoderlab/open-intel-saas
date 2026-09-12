"""Health endpoint: liveness plus the runtime module state."""

from fastapi import APIRouter

from modules.platform.domain.models import ModuleState


def build_health_router(states: list[ModuleState]) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/healthz")
    def healthz() -> dict:
        return {
            "status": "ok",
            "modules": [
                {
                    "name": s.name,
                    "title": s.title,
                    "required": s.required,
                    "enabled": s.enabled,
                }
                for s in states
            ],
        }

    return router
