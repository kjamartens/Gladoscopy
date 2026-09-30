"""Shared pytest fixtures for the Glados-PycroManager test suite.

The fixtures here are intentionally tiny — they cover the three things
multiple test files need: a redirected AppData directory, a mocked
Micro-Manager core, and the in-memory `FakeMicroscopeInterfaceLayer`.
Anything bigger should live in its own conftest under `tests/<area>/`.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:  # only for type hints; not imported at runtime
    pass


@pytest.fixture
def tmp_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `appdirs.user_data_dir` to a temp directory.

    Both `Shared_data` (`glados_pycromanager.GUI.sharedFunctions`) and
    `utils.storeSharedData_GlobalData` resolve the JSON state file via
    `appdirs.user_data_dir()`. Patching that single call point makes
    every test that touches the JSON layer fully sandboxed.

    Returns the redirected directory (its `Glados-PycroManager`
    subdirectory is created lazily by the production code).
    """
    target = tmp_path / "appdata"
    target.mkdir()
    monkeypatch.setattr(
        "glados_pycromanager.GUI.sharedFunctions.appdirs.user_data_dir",
        lambda *a, **kw: str(target),
    )
    # `utils.storeSharedData_GlobalData` re-imports appdirs at module
    # scope, so patch that one too if/when a test routes through it.
    monkeypatch.setattr(
        "glados_pycromanager.GUI.utils.appdirs.user_data_dir",
        lambda *a, **kw: str(target),
        raising=False,
    )
    return target


@pytest.fixture
def mock_core() -> MagicMock:
    """Plain `MagicMock` standing in for a Micro-Manager core.

    Tests that only need a "core-shaped object" (no per-method behavior)
    should grab this. Tests that need backend-aware dispatch should use
    `fake_mil` (or `_mock_core` in `test_microscope_interface_layer.py`,
    which builds a `MagicMock(spec=...)` of the right backend class).
    """
    core = MagicMock()
    core.getDeviceList.return_value = []
    core.getCameraDevice.return_value = "FakeCam"
    return core


@pytest.fixture
def fake_mil():
    """Return a fresh `FakeMicroscopeInterfaceLayer` instance.

    The fake mirrors the `MicroscopeInterfaceLayer` public surface
    against in-memory state and is added in Phase 5.3
    (`tests/fakes/fake_mil.py`). Import is deferred so the conftest
    keeps loading even before that file lands.
    """
    from tests.fakes.fake_mil import FakeMicroscopeInterfaceLayer

    return FakeMicroscopeInterfaceLayer()
