"""PyQt5 imported before pymmcore must not crash CMMCore (glados_pycromanager/win_runtime.py).

Only a uv / python-build-standalone interpreter actually exhibits the crash; on a
conda-based one (whose own MSVCP140.dll loads first) these pass either way.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows DLL loading")


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)


def test_cmmcore_survives_qt_imported_first() -> None:
    result = _run("import glados_pycromanager, PyQt5.QtWidgets, pymmcore; pymmcore.CMMCore(); print('ok')")
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr[-2000:]}"
    assert result.stdout.strip() == "ok"


def test_preload_leaves_an_already_loaded_runtime_alone() -> None:
    result = _run("import PyQt5.QtCore\n"
                  "from glados_pycromanager.win_runtime import preload_system_msvcp140\n"
                  "print(preload_system_msvcp140())")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "None"
