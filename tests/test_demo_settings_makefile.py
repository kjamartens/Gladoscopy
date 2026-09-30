"""Wiring guard for `make run-demo-smlm` and its demo_settings.mk.

Text-level only — no Make, no Qt, no hardware. The point is that a typo in a
variable name between the settings file and the recipe cannot go unnoticed
(the symptom would be a silently empty CLI flag, which argparse turns into a
confusing "--config requires --backend" error).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_VARS = (
    "DEMO_BACKEND",
    "DEMO_MM_PATH",
    "DEMO_CONFIG",
    "DEMO_BUFFER_MB",
    "DEMO_MAX_MEMORY_MB",
)


@pytest.fixture(scope="module")
def demo_settings() -> str:
    path = REPO_ROOT / "demo_settings.mk"
    assert path.is_file(), "demo_settings.mk is missing from the repo root"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def makefile() -> str:
    return (REPO_ROOT / "Makefile").read_text(encoding="utf-8")


@pytest.mark.parametrize("var", DEMO_VARS)
def test_demo_settings_defines_var_with_soft_assignment(demo_settings: str, var: str) -> None:
    """`?=` (not `=`) so `make run-demo-smlm DEMO_BUFFER_MB=1024` still wins."""
    assert re.search(rf"^{var}\s*\?=", demo_settings, re.MULTILINE), (
        f"{var} must be defined in demo_settings.mk with ?="
    )


def test_makefile_includes_demo_settings(makefile: str) -> None:
    # Leading `-` so a missing file is not a hard parse error for every target.
    assert "-include demo_settings.mk" in makefile


def test_run_demo_smlm_target_is_declared(makefile: str) -> None:
    assert re.search(r"^run-demo-smlm:", makefile, re.MULTILINE)
    phony = re.search(r"^\.PHONY:(.*?)(?=^\S)", makefile, re.MULTILINE | re.DOTALL)
    assert phony is not None
    assert "run-demo-smlm" in phony.group(1)


def _recipe(makefile: str) -> str:
    """The run-demo-smlm block: from its rule line (not the comment above it,
    which also mentions the target name) to the next blank line."""
    match = re.search(r"^run-demo-smlm:.*?(?=\n\n)", makefile, re.MULTILINE | re.DOTALL)
    assert match is not None, "could not locate the run-demo-smlm recipe"
    return match.group(0)


@pytest.mark.parametrize("var", DEMO_VARS)
def test_run_demo_smlm_recipe_uses_every_var(makefile: str, var: str) -> None:
    assert f"$({var})" in _recipe(makefile), f"run-demo-smlm's recipe never passes {var}"


@pytest.mark.parametrize(
    "flag", ["--backend", "--config", "--mm-path", "--buffer-mb", "--max-memory-mb"]
)
def test_run_demo_smlm_passes_the_cli_override_flags(makefile: str, flag: str) -> None:
    assert flag in _recipe(makefile)


def test_python_path_separator_follows_the_recipe_shell(makefile: str) -> None:
    """The Windows `$(subst /,\\,...)` must be conditional on the recipe shell.

    GNU make uses sh.exe as SHELL whenever it finds one on PATH (Git for Windows,
    scoop, MSYS) even when started from PowerShell/cmd, and sh reads the `\\S` in
    `.venv\\Scripts\\python.exe` as an escape -- every run/test target then dies with
    `.venvScriptspython.exe: command not found`.
    """
    assert "_WINPATH" in makefile
    assert "ifeq ($(findstring sh,$(notdir $(SHELL))),sh)" in makefile
    assert "$(call _WINPATH,$(_VENV_PYTHON))" in makefile
    assert "$(subst /,\\,$(_VENV_PYTHON))" not in makefile


def test_run_demo_is_still_the_bundled_auto_demo(makefile: str) -> None:
    """Regression guard: claude_throughput_project.md's verification runs use it."""
    assert re.search(
        r"^run-demo:.*\n(?:#.*\n)*\t.*GUI_napari --auto-demo\s*$", makefile, re.MULTILINE
    )
