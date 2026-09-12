"""Fixtures for the product scaffold tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def modules_root(tmp_path: Path) -> Iterator[Path]:
    """A fake modules/ tree: platform (required) + two optional modules."""
    root = tmp_path / "modules"
    for name, required in (("platform", True), ("research", False), ("analytics", False)):
        module_dir = root / name
        module_dir.mkdir(parents=True)
        (module_dir / "module.toml").write_text(
            f"name = \"{name}\"\ntitle = \"{name.title()} module\"\nrequired = {str(required).lower()}\n"
        )
    yield root
