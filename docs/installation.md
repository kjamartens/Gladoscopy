# Installation

Glados runs on Windows. It installs into its own Python environment (a `.venv` folder inside the
Glados folder) using [uv](https://docs.astral.sh/uv/), which also downloads the right Python
version (3.13) itself. You do not need conda, or Python installed beforehand.

## Requirements

- **Git**: <https://git-scm.com/download/win> (or `winget install Git.Git`).
- **uv**: `winget install astral-sh.uv`, or see the
  [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/). The install
  script below offers to install it for you if it is missing.
- **Micro-Manager 2.0**, a recent nightly build:
  <https://micro-manager.org/Micro-Manager_Nightly_Builds>

## Install

1. Get the code:

    ```batch
    git clone https://github.com/kjamartens/Gladoscopy.git
    ```

2. Double-click `install_windows.bat` in that folder (or run it from a terminal). It creates
   `.venv`, installs Glados and its dependencies (a few GB; the first time takes several minutes),
   and offers to add Glados to the Start Menu. Pin that entry to the taskbar for a one-click start.

The same steps by hand, from the Glados folder:

```batch
uv venv --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -e .
.venv\Scripts\python.exe -m glados_pycromanager.shortcuts install
```

**Update:** `git pull`, then run `install_windows.bat` again. Do not upgrade `pycromanager` or
`pymmcore` on their own: Glados pins the versions it was tested with, and a mismatched `pymmcore`
cannot load the Micro-Manager device adapters.

**Developers:** with `make` installed (e.g. `winget install ezwinports.make`), `make dev` does the
same install plus the test, lint and docs tools. See [Contributing](developer/contributing.md).

## Micro-Manager setup

Glados asks which backend to use when it starts:

- **PyMMCorePlus** or **Python** (recommended; fastest live display): point the start dialog at
  your Micro-Manager installation folder and your `.cfg` configuration file. Micro-Manager itself
  does not need to be running.
- **Java (deprecated)**: start Micro-Manager first, enable *Tools → Options → Run pycro-manager
  server on port 4827*, and stop any live mode or acquisition. Use this only when you need a
  feature of the Java Micro-Manager engine.

The folder and configuration fields remember the last 20 values you used (the arrow next to each
field).

To try Glados without hardware, use the PyMMCorePlus backend with Micro-Manager's
`MMConfig_demo.cfg`, or start it with `--auto-demo` (below).

## Starting Glados

- **Start Menu / taskbar**: the "Glados" entry the installer created. "Glados (last setup)" skips
  the start dialog and reuses the previous backend and configuration; "Glados (debug console)"
  keeps a console window open for error messages. Re-create the entries with `make shortcuts` or
  `.venv\Scripts\python.exe -m glados_pycromanager.shortcuts install`.
- **Terminal**: `.venv\Scripts\glados.exe` from the Glados folder (or `glados` after
  `.venv\Scripts\activate`). Useful options:
    - `--last`: start with the backend and configuration used last time, without the dialog.
    - `--auto-demo`: start the pymmcore-plus demo install with `MMConfig_demo.cfg`, no hardware
      needed (run `mmcore install` once to download it).
    - `--backend {JAVA,Python,PyMMCorePlus} --config <file.cfg> [--mm-path <folder>]`: skip the
      dialog with explicit settings.
- **Inside napari** (Java backend, with Micro-Manager already running): start
  `.venv\Scripts\napari.exe`, then *Plugins → Glados-PycroManager → Run Glados-PycroManager*.
- **Debugging**: run `glados_pycromanager/GUI/GUI_napari.py` from your IDE with `.venv` as the
  interpreter, for full debugger access.

A second launch while Glados is running brings the running window to the front instead of
starting another copy.

## Faster startup (optional)

A *cold* start (the first after a reboot, or after an install or update) can take several times as
long as a warm one: on a test laptop ~60 s against ~23 s. Most of that difference is reading
thousands of small library files from disk, each of which the virus scanner checks. Two things
help, and neither is applied for you:

1. **Precompile the bytecode after installing or updating.** `install_windows.bat` already does
   this. Otherwise Python writes these files itself on the first launch, so this only speeds up
   that one launch:

    ```batch
    .venv\Scripts\python.exe -m compileall -q -j 0 glados_pycromanager .venv\Lib\site-packages
    ```

    It takes about a minute. `SyntaxWarning`s from third-party packages are harmless.

2. **A Microsoft Defender exclusion for the `.venv` folder.** This is often the biggest cold-start
   saving, but it is a security decision: files in an excluded folder are no longer scanned. On a
   managed (institute) PC, ask your IT department; their policy may forbid or override it. On a PC
   you administer, run in an *administrator* PowerShell, with your own path:

    ```powershell
    Add-MpPreference -ExclusionPath "C:\GitHub\Gladoscopy\.venv"
    ```

    Remove it again with `Remove-MpPreference -ExclusionPath "C:\GitHub\Gladoscopy\.venv"`.

Problems on the first run? See [Troubleshooting](user-guide/troubleshooting.md).
