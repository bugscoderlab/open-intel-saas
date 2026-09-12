"""Domain model of the module system.

Pure dataclasses only — no FastAPI, no framework imports (plan §14.2,
enforced by import-linter contracts).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDefinition:
    """A module discovered on disk via its ``module.toml`` manifest."""

    name: str
    title: str
    required: bool = False


@dataclass(frozen=True)
class ModuleState:
    """A discovered module plus its runtime enable/disable state."""

    name: str
    title: str
    required: bool
    enabled: bool
