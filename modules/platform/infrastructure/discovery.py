"""Filesystem discovery of product modules via their ``module.toml`` manifests."""

import tomllib
from pathlib import Path

from modules.platform.domain.models import ModuleDefinition


def discover_modules(modules_root: Path) -> list[ModuleDefinition]:
    """Return the module definitions declared under ``modules_root``.

    A directory under ``modules_root`` containing a ``module.toml`` is a
    module. Discovery order is alphabetical for deterministic state.
    """
    if not modules_root.is_dir():
        return []
    definitions = []
    for manifest in sorted(modules_root.glob("*/module.toml")):
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        definitions.append(
            ModuleDefinition(
                name=data["name"],
                title=data.get("title", data["name"]),
                required=bool(data.get("required", False)),
            )
        )
    return definitions
