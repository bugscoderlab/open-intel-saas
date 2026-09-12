"""Health endpoint: liveness plus the runtime module state."""

from fastapi import APIRouter
from pydantic import BaseModel

from modules.platform.domain.models import ModuleState


class ModuleStatePayload(BaseModel):
    name: str
    title: str
    required: bool
    enabled: bool


class HealthPayload(BaseModel):
    status: str
    modules: list[ModuleStatePayload]


def build_health_router(states: list[ModuleState]) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get(
        "/healthz",
        summary="Service health",
        description="Liveness probe plus the runtime state of every product module.",
        response_model=HealthPayload,
    )
    def healthz() -> HealthPayload:
        return HealthPayload(
            status="ok",
            modules=[
                ModuleStatePayload(
                    name=s.name,
                    title=s.title,
                    required=s.required,
                    enabled=s.enabled,
                )
                for s in states
            ],
        )

    return router
