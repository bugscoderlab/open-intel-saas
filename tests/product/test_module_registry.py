"""Module registry: which modules exist, which are enabled, what is required."""

import pytest

from modules.platform.application.registry import build_module_states
from modules.platform.domain.models import ModuleDefinition


def definition(name: str, *, required: bool = False) -> ModuleDefinition:
    """Build a module definition for tests."""
    return ModuleDefinition(name=name, title=name.title(), required=required)


PLATFORM = definition("platform", required=True)
RESEARCH = definition("research")
ANALYTICS = definition("analytics")
ALL_MODULES = [PLATFORM, RESEARCH, ANALYTICS]


def test_every_discovered_module_gets_a_state() -> None:
    """Each discovered module produces exactly one runtime state."""
    states = build_module_states(ALL_MODULES, disabled=set())
    assert {s.name for s in states} == {"platform", "research", "analytics"}


def test_nothing_disabled_means_everything_enabled() -> None:
    """With no disables, every module runs."""
    states = build_module_states(ALL_MODULES, disabled=set())
    assert all(s.enabled for s in states)


def test_disabled_optional_module_is_reported_not_deleted() -> None:
    """A disabled module stays visible in state with enabled=False."""
    states = build_module_states(ALL_MODULES, disabled={"research"})
    by_name = {s.name: s for s in states}
    assert by_name["research"].enabled is False
    assert by_name["analytics"].enabled is True


def test_disabling_the_platform_module_is_rejected() -> None:
    """The required platform module can never be disabled."""
    with pytest.raises(ValueError, match="platform"):
        build_module_states(ALL_MODULES, disabled={"platform"})


def test_disabling_an_unknown_module_is_rejected() -> None:
    """Unknown names in the disabled list fail fast (typo protection)."""
    with pytest.raises(ValueError, match="typo"):
        build_module_states(ALL_MODULES, disabled={"typo"})


def test_platform_module_missing_is_rejected() -> None:
    """Startup input without the platform module is invalid."""
    with pytest.raises(ValueError, match="platform"):
        build_module_states([RESEARCH], disabled=set())
