"""Phase 10.11 — AppData plugin walk tolerates missing / unreadable dirs.

The plugin loader walks ``<appdata>/Glados-PycroManager/<sub>/`` looking
for `.py` files the user dropped there. A missing or permission-denied
folder must not bring the app down — it logs and continues.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from glados_pycromanager.plugins import discovery


def test_nonexistent_folder_yields_no_modules(tmp_path: Path) -> None:
    missing = tmp_path / "definitely-not-here"
    successes, failures = discovery.load_node_modules(missing, prefix="testpkg")
    assert successes == []
    assert failures == []


def test_iter_module_files_on_missing_path_returns_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "ghost"
    with caplog.at_level(logging.DEBUG, logger=discovery.logger.name):
        result = discovery._iter_module_files(missing)
    assert result == []
    # debug log explaining the skip
    assert any("does not exist" in rec.message for rec in caplog.records)


def test_iter_module_files_path_is_file_not_dir(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    afile = tmp_path / "iam_a_file.txt"
    afile.write_text("", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger=discovery.logger.name):
        result = discovery._iter_module_files(afile)
    assert result == []
    assert any("not a directory" in rec.message for rec in caplog.records)


def test_iter_module_files_permission_error_is_logged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Simulate a PermissionError on iterdir() — must log + return []."""
    target = tmp_path / "guarded"
    target.mkdir()

    real_iterdir = Path.iterdir

    def boom(self: Path):
        if self == target:
            raise PermissionError("simulated locked folder")
        yield from real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", boom)
    with caplog.at_level(logging.WARNING, logger=discovery.logger.name):
        result = discovery._iter_module_files(target)
    assert result == []
    assert any(
        "unreadable" in rec.message and "simulated locked folder" in rec.message
        for rec in caplog.records
    )


def test_load_node_modules_on_missing_folder_does_not_raise(
    tmp_path: Path,
) -> None:
    """load_node_modules itself is the public surface — it must shrug."""
    successes, failures = discovery.load_node_modules(
        tmp_path / "no-such-dir",
        prefix="testpkg",
    )
    assert successes == failures == []


def test_user_appdata_dir_permission_error_returns_path(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When mkdir() fails the helper logs but still returns a path so
    callers can pass it to load_node_modules and get an empty result."""

    def fail_mkdir(self, *args, **kwargs):
        raise PermissionError("simulated locked appdata")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with caplog.at_level(logging.WARNING, logger=discovery.logger.name):
        result = discovery.user_appdata_dir_for(("AutonomousMicroscopy", "Test_Folder"))
    assert isinstance(result, Path)
    assert "Test_Folder" in str(result)
    assert any("Could not create" in rec.message for rec in caplog.records)
