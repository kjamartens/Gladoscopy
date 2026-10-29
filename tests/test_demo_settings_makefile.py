"""Wiring guard for `make run-demo-smlm` and its demo_settings.mk.

Text-level, plus one check against the real Windows recipe shells — no Make, no Qt, no hardware. The point is that a typo in a
variable name between the settings file and the recipe cannot go unnoticed
(the symptom would be a silently empty CLI flag, which argparse turns into a
confusing "--config requires --backend" error).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
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


def test_venv_python_is_a_quoted_forward_slash_path(makefile: str) -> None:
    """The Windows `.venv` interpreter must be one form that runs in both recipe shells.

    GNU make's recipe shell is sh.exe when one is on PATH (Git Bash, scoop, MSYS)
    and cmd.exe otherwise, while `$(SHELL)` reads "sh.exe" either way -- so keying
    the separator on it gave cmd `.venv/Scripts/python.exe`, which cmd parses as
    `.venv` plus a `/Scripts` switch (a plain Git for Windows install only puts
    `git\cmd` on PATH, so this is the common case). sh, in turn, reads the `\S`
    of the backslash form as an escape.
    """
    assert 'PYTHON ?= $(if $(wildcard $(_VENV_PYTHON)),"$(_VENV_PYTHON)",python)' in makefile
    assert "_WINPATH" not in makefile


def _shells() -> list[list[str]]:
    shells = [["cmd.exe", "/d", "/c"]]
    git = shutil.which("git")
    if git:
        sh = Path(git).resolve().parents[1] / "usr" / "bin" / "sh.exe"
        if sh.is_file():
            shells.append([str(sh), "-c"])
    return shells


@pytest.mark.skipif(sys.platform != "win32", reason="Windows recipe shells")
@pytest.mark.parametrize("shell", _shells(), ids=lambda s: Path(s[0]).stem)
def test_quoted_forward_slash_path_runs_in_recipe_shell(tmp_path: Path, shell: list[str]) -> None:
    """What the assertion above relies on, checked against the real shells."""
    exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    exe.parent.mkdir(parents=True)
    shutil.copy(Path(os.environ["SystemRoot"]) / "System32" / "hostname.exe", exe)
    # Run the line from a script file: Python's argv quoting would turn the quotes
    # into \", which cmd and the various MSYS sh builds each parse differently.
    line = '".venv/Scripts/python.exe"'
    if shell[0] == "cmd.exe":
        script = tmp_path / "recipe.bat"
        script.write_text(f"@{line}\r\n", encoding="ascii")
        command = [*shell, str(script)]
    else:
        script = tmp_path / "recipe.sh"
        script.write_text(f"{line}\n", encoding="ascii")
        command = [shell[0], script.name]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_run_demo_is_still_the_bundled_auto_demo(makefile: str) -> None:
    """Regression guard: claude_throughput_project.md's verification runs use it."""
    assert re.search(
        r"^run-demo:.*\n(?:#.*\n)*\t.*GUI_napari --auto-demo\s*$", makefile, re.MULTILINE
    )
