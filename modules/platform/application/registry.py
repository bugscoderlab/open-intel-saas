"""Application layer of the platform module.

Use cases over the domain model. The module registry decides which
discovered modules run: the platform module is required; everything else
can be disabled through configuration while the API still starts
(plan §20).
"""

from typing import Iterable, Protocol

from modules.platform.domain.models import ModuleDefinition, ModuleState

PLATFORM_MODULE = "platform"


class ModuleConfig(Protocol):
    """Configuration the registry needs, provided by infrastructure."""

    @property
    def disabled_modules(self) -> Iterable[str]: ...


def build_module_states(
    definitions: list[ModuleDefinition], disabled: Iterable[str]
) -> list[ModuleState]:
    """Resolve discovered modules + configuration into runtime states.

    Raises:
        ValueError: if the required platform module is absent, if the
            platform module is disabled, or if the disabled list names an
            unknown module (fail fast on configuration typos).
    """
    names = {d.name for d in definitions}
    if PLATFORM_MODULE not in names:
        raise ValueError(
            f"required module '{PLATFORM_MODULE}' is not present in discovered modules"
        )
    unknown = set(disabled) - names
    if unknown:
        raise ValueError(f"unknown modules in disabled list: {sorted(unknown)}")
    if PLATFORM_MODULE in disabled:
        raise ValueError(f"required module '{PLATFORM_MODULE}' cannot be disabled")
    return [
        ModuleState(
            name=d.name,
            title=d.title,
            required=d.required,
            enabled=d.name not in disabled,
        )
        for d in definitions
    ]
