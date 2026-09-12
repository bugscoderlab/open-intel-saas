"""HTTP seam: the app starts with optional modules disabled and reports them."""

from collections.abc import Iterable

import pytest
from fastapi.testclient import TestClient

from modules.platform.api.app import create_app
from modules.platform.infrastructure.discovery import discover_modules
from modules.platform.infrastructure.settings import Settings


def make_client(modules_root, disabled: Iterable[str] = ()) -> TestClient:
    config = Settings(disabled_modules=frozenset(disabled))
    registry = discover_modules(modules_root)
    return TestClient(create_app(config=config, registry=registry))


def test_health_reports_ok_and_module_states(modules_root):
    client = make_client(modules_root, disabled={"analytics"})
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    states = {m["name"]: m for m in body["modules"]}
    assert states["platform"]["enabled"] is True
    assert states["platform"]["required"] is True
    assert states["research"]["enabled"] is True
    assert states["analytics"]["enabled"] is False


def test_app_starts_when_optional_module_disabled(modules_root):
    client = make_client(modules_root, disabled={"research", "analytics"})
    assert client.get("/healthz").status_code == 200


def test_app_refuses_to_start_without_platform_module(tmp_path):
    empty_root = tmp_path / "modules"
    empty_root.mkdir()
    (empty_root / "research").mkdir()
    (empty_root / "research" / "module.toml").write_text(
        'name = "research"\ntitle = "Research"\n'
    )
    config = Settings(disabled_modules=frozenset())
    registry = discover_modules(empty_root)
    with pytest.raises(RuntimeError, match="platform"):
        create_app(config=config, registry=registry)
