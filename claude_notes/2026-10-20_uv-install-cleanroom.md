# 2026-10-20 — uv/.venv install and clean-room install test

## Key findings, decisions, results

- **Conda dropped**: `environment.yaml`, `win_create_env.bat` and `make env` removed. New `install_windows.bat` (git + uv only; offers to install uv; `/y` unattended) is the end-user route. `make dev` is the developer route.
- **Committed and pushed** (at the user's request, so others can test) as branch `docs/uv-install` on origin, no PR: `6a17b75` fix(win) MSVCP140 preload, `167166c` fix(build) Makefile, `bf22662` build: install_windows.bat + docs. Testers: `git clone -b docs/uv-install https://github.com/kjamartens/Gladoscopy.git`, then run `install_windows.bat`. These notes are not committed (`claude_notes/` is gitignored).
- **Clean-room cold install works**: `install_windows.bat /y` took 900 s (8.3 min download of 230 packages, 2 min install, 2.7 min bytecode compile). uv downloaded Python 3.13.14 itself; the 3 shortcuts were created.
- **Bug 1 (major): uv's Python + PyQt5 + pymmcore crash.** If Qt is imported before pymmcore, PyQt5's bundled old `MSVCP140.dll` wins and `CMMCore()` access-violates. Miniconda's Python (which the user's `.venv` is built on) masks it. Fix: `glados_pycromanager/win_runtime.py` preloads `System32\msvcp140.dll`, called from the package `__init__` and `tests/conftest.py`. Test: `tests/test_win_runtime.py`.
- **Bug 2: `make dev` broke without `sh.exe` on PATH** (a stock Git for Windows install only adds `git\cmd`). `$(SHELL)` reads `sh.exe` even when cmd is used, so `_WINPATH` chose forward slashes. Fix: `PYTHON` is the quoted path `".venv/Scripts/python.exe"`, which works in both shells; a test runs it in real cmd and sh.
- **Bug 3**: the `@#` comment recipe line in `dev` ran as a command under cmd; it's now a make comment.
- The pymmcore 12.5.1 GUI crash had the same cause as bug 1. A temporary pin to 12.5.0 was **reverted** after the fix.
- Final results: clean uv install with `make dev` passed in 52 s; fast suite 1482 + 1 passed (~70 s); GUI smoke launch ready in 9.7 s; the user's own `.venv` fast suite: 1483 passed in 47 s.

## Details

**Changes**: Makefile (uv from PATH via `_UV_ON_PATH`, `$(UV)` for build, quoted `PYTHON`, no `env` target), `install_windows.bat`, `.gitattributes` (`*.bat`/`*.cmd` CRLF), README quick install, UserManual install/MM setup/running sections and TOC, CONTRIBUTING, CLAUDE.md, the `install_check`/`shortcuts` hint text, the `profile_startup.ps1` header, and `test_demo_settings_makefile.py` (the old `_WINPATH` test replaced by a behavioural test).

**Clean-room method** (no Sandbox/Hyper-V/Docker on this laptop): a fresh `git init` copy of the tree in `%LOCALAPPDATA%\gcr`; PATH = Windows + Git + a copied `uv.exe`; `UV_CACHE_DIR` cold; `UV_PYTHON_PREFERENCE=only-managed`; `APPDATA` redirected. GUI smoke: a runpy launcher patching `appdirs.user_data_dir` plus `NAPARI_CONFIG`, running `--auto-demo --startup-exit --allow-second-instance`. Scripts were in the session scratchpad.

**Errors hit along the way**:
- The harness sets `NoDefaultCurrentDirectoryInExePath=1`, so cmd won't run a bare `.bat` from the cwd.
- Python argv quoting turns `"` into `\"`, which cmd and MSYS sh parse differently, so the shell tests run from script files.
- A scratch `bisect.py` shadowed the stdlib module (my own artifact).
- The package-version bisect showed the crash was not version drift; the interpreter was the difference (miniconda 3.13.5 vs python-build-standalone 3.13.14).

**Open items**:
- ~74 packages float between installs (pymmcore, pymmcore-plus, pycromanager from git main, …); consider a lock file.
- PyQt6 gets installed alongside PyQt5 (via `napari[all]`).
- The napari-plugin route imports Qt before glados; not covered, but it only uses the Java `Core()`.
- The user's `.venv` is still conda-based (rebuild with `make clean` then `make dev`).
- `%LOCALAPPDATA%\gcr` (several GB) is still on disk.
- The README clone command checks out `main`; testers of the branch need `-b docs/uv-install` until it is merged.
- Commit history note: the first commit attempt swept the already-staged `git rm` deletions into the fix(win) commit. The local commits were redone (reset to `b7a7bf9`, recommitted with the same messages) before pushing.
