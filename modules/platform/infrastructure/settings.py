"""Runtime configuration for the platform module.

Environment-driven, no framework dependencies.
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
    """

    disabled_modules: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        environ = os.environ if environ is None else environ
        raw = environ.get(DISABLED_MODULES_ENV_VAR, "")
        disabled = frozenset(
            item.strip() for item in raw.split(",") if item.strip()
        )
        return cls(disabled_modules=disabled)
