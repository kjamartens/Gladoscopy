"""Phase 10.9 — validate headless-start dialog inputs.

The headless dialog gates its Start button on these checks. We test
the pure validator directly — wiring into Qt is straightforward and
inspected by hand.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from glados_pycromanager.GUI.headless_validation import (
    headless_inputs_are_valid,
    validate_headless_inputs,
)


@pytest.fixture
def valid_paths(tmp_path: Path) -> tuple[str, str]:
    mm_dir = tmp_path / "Micro-Manager-2.0"
    mm_dir.mkdir()
    cfg = tmp_path / "demo.cfg"
    cfg.write_text("# fake config\n", encoding="utf-8")
    return str(mm_dir), str(cfg)


def test_happy_path_returns_no_errors(valid_paths: tuple[str, str]) -> None:
    mm, cfg = valid_paths
    assert validate_headless_inputs(mm, cfg) == []
    assert headless_inputs_are_valid(mm, cfg) is True


def test_empty_mm_path_is_invalid(valid_paths: tuple[str, str]) -> None:
    _, cfg = valid_paths
    errors = validate_headless_inputs("", cfg)
    assert any("path is empty" in e for e in errors)
    assert headless_inputs_are_valid("", cfg) is False


def test_whitespace_mm_path_is_invalid(valid_paths: tuple[str, str]) -> None:
    _, cfg = valid_paths
    errors = validate_headless_inputs("   ", cfg)
    assert any("path is empty" in e for e in errors)


def test_nonexistent_mm_path_is_invalid(
    tmp_path: Path, valid_paths: tuple[str, str]
) -> None:
    _, cfg = valid_paths
    bogus = str(tmp_path / "definitely-not-here")
    errors = validate_headless_inputs(bogus, cfg)
    assert any("does not exist" in e for e in errors)


def test_mm_path_is_file_not_dir(
    tmp_path: Path, valid_paths: tuple[str, str]
) -> None:
    _, cfg = valid_paths
    a_file = tmp_path / "fake-file"
    a_file.write_text("", encoding="utf-8")
    errors = validate_headless_inputs(str(a_file), cfg)
    assert any("not a directory" in e for e in errors)


def test_empty_config_file_is_invalid(valid_paths: tuple[str, str]) -> None:
    mm, _ = valid_paths
    errors = validate_headless_inputs(mm, "")
    assert any("Config file is empty" in e for e in errors)


def test_nonexistent_config_file_is_invalid(
    tmp_path: Path, valid_paths: tuple[str, str]
) -> None:
    mm, _ = valid_paths
    errors = validate_headless_inputs(mm, str(tmp_path / "ghost.cfg"))
    assert any("does not exist" in e for e in errors)


def test_config_file_wrong_suffix_is_invalid(
    tmp_path: Path, valid_paths: tuple[str, str]
) -> None:
    mm, _ = valid_paths
    txt = tmp_path / "not-a-cfg.txt"
    txt.write_text("", encoding="utf-8")
    errors = validate_headless_inputs(mm, str(txt))
    assert any("must end with '.cfg'" in e for e in errors)


def test_config_file_path_is_directory_not_file(
    tmp_path: Path, valid_paths: tuple[str, str]
) -> None:
    mm, _ = valid_paths
    not_a_file = tmp_path / "config-dir"
    not_a_file.mkdir()
    errors = validate_headless_inputs(mm, str(not_a_file))
    assert any("not a regular file" in e for e in errors)


def test_uppercase_cfg_suffix_accepted(
    tmp_path: Path, valid_paths: tuple[str, str]
) -> None:
    mm, _ = valid_paths
    cfg = tmp_path / "Demo.CFG"
    cfg.write_text("", encoding="utf-8")
    errors = validate_headless_inputs(mm, str(cfg))
    assert errors == []


def test_both_invalid_returns_two_messages(tmp_path: Path) -> None:
    errors = validate_headless_inputs("", "")
    assert len(errors) == 2
