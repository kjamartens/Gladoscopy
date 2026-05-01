# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Glados-pycromanager: a Napari-based UI for Pycromanager (python-Micromanager) plus a node-graph framework for autonomous microscopy. Runs either standalone (own QApplication) or as a Napari plugin.

## Environment & install

- Python 3.13 is required (`pyproject.toml`, `environment.yaml`). The user manual still mentions 3.10 — that is outdated; do not follow it.
- One-shot Windows setup: run `win_create_env.bat`. It creates a conda env named `GladosEnv` from `environment.yaml`, then `uv pip install -e .` for editable install.
- The dependency pin set in `pyproject.toml` is strict (numpy/pandas/scipy/napari/pyqt5/tensorflow all hard-pinned). Avoid casually bumping them; the GUI is sensitive to napari/PyQt5 versions.
- Note: line 40 of `pyproject.toml` (`napari[all]==0.7.0,`) has an unterminated string literal — be aware if editing the file.

## Running

The package installs four equivalent console scripts, all pointing at `glados_pycromanager.GUI.GUI_napari:main`:

```
glados
glados-pycromanager
gladospycromanager
glados-pycro-manager
```

Other entry points:
- `napari` then *Plugins → Glados-PycroManager → Run Glados-PycroManager* — uses `_dock_widget:MainWidget` (the napari plugin path; assumes a Pycromanager Java server on port 4827 is already up — `Core()` is called directly with no headless prompt).
- Run `glados_pycromanager/GUI/GUI_napari.py` from your IDE for full debugger access. The file contains a `sys.path.insert` shim so it works when not installed.

There is no test suite, lint config, or build script in the repo — `Test.py` and `test.ipynb` at the root are ad-hoc scratch files (DIPlib FFT benchmark, etc.), not a test runner. Do not invent `pytest` / `ruff` invocations.

## Architecture

### Backends — `Core/microscopeInterfaceLayer.py` (MIL)

`MicroscopeInterfaceLayer` is the abstraction over three mutually exclusive backends, identified via the `MicroscopeInstance` enum: `PYCROMANAGER_JAVA`, `PYCROMANAGER_PYTHON`, `MMCORE_PLUS`. Code that needs to talk to the microscope should go through `MIL`, branching on `mil.get_microscope_interface()` (alias `MI()` / `get_MI()`). The user picks the backend in the headless start dialog (`headlessGUI` in `GUI_napari.py`) — this writes `shared_data.config.micromanager_config.headless_backend`.

`Core/MDAGlados.py` is the multi-dimensional acquisition layer that talks to MIL.

### Shared state — `GUI/sharedFunctions.py`

`Shared_data` is the single object passed everywhere (UI, worker threads, napari plugins, autonomous microscopy nodes). It holds `core`, the MIL instance, config dataclasses, analysis-thread lists (`LoggingList` is a list subclass that emits Qt signals on mutation), and live/acquisition state flags. When adding cross-component state, add it as a field on `Shared_data` rather than a global.

### UI — `GUI/`

- `GUI_napari.py` — standalone entry. Builds a `headlessGUI` for backend choice, spawns Napari, runs `runNapariPycroManager` in a `Worker`/`QThread`. Sets `NAPARI_ASYNC=1` and `NAPARI_OCTREE=1` *before* importing napari.
- `_dock_widget.py` — napari plugin entry. `MainWidget` constructs `Shared_data`, calls `pycromanager.Core()` directly, and adds four dock widgets — all of which inherit `GladosWidget`:
  - `MMConfigWidget` — Micro-Manager config groups, stages, ROI (`microManagerControlsUI_plugin`)
  - `MDAWidget` — Multi-D acquisition (`MDAGlados_plugin`)
  - `AutonomousMicroscopyWidget` — recipe graph (`autonomousMicroscopy_plugin`)
  - `GladosSlidersWidget` — laser controls (`gladosSliders_plugin`)
  Pattern: the parent `MainWidget` creates `core`, `shared_data`, `MM_JSON`, `livestate`, and child widgets read them off `parent.*` in their `__init__`.
- `GUI/napariGlados.py` — `napariHandler` and the real-time visualisation/analysis loop (`napariUpdateLive`, etc.). Uses `napari.qt.thread_worker` and yield-based generators, which is why several update functions live at module scope rather than inside a class.
- `GUI/nodz/` — vendored Nodz graph editor, used to render and edit autonomous-microscopy recipes (JSON, e.g. `Showcase_Basic1.json`). Recipes have three regions: Initialisation (pink), Scoring (green), Acquisition (yellow).
- Hostname gate: `runNapariPycroManagerWrap` flips `includeCustomUI=True` when `'SMIPC' in platform.node()` — site-specific UI add-ons.

### Autonomous microscopy — `AutonomousMicroscopy/`

- `MainScripts/Main.py`, `FunctionHandling.py`, `HelperFunctions.py` — graph executor, function discovery, kwarg introspection.
- `Analysis_Measurements/` — measurement nodes (StarDist, AverageImage, etc.).
- `Real_Time_Analysis/` — RT analysis nodes (FFT, pSMLM, sharpness, BioImage Model Zoo, frame counters).
- `CustomFunctions/` — site-defined helpers (autofocus, stroboscopic lasers).

**Plugin discovery (important):** the `__init__.py` in each of these three folders does two things on import:
1. `load_additional_modules` walks the folder, appends every non-`__init__` `.py` to `__all__`, and `from .<module> import *`s it.
2. It then walks `appdirs.user_data_dir()/Glados-PycroManager/<subfolder>/` and imports any `.py` files dropped there via `importlib`.

So **users add new analysis/RT/custom nodes by dropping a `.py` into the AppData folder, not into the source tree.** When searching for a node implementation, check both locations. Adding a file to one of these folders without proper top-level functions will cause it to be imported but not appear as a node.

### Path / import conventions

Most modules begin with this shim because the codebase supports both `pip install -e .` and "open the file in an IDE":
```python
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
```
Keep it on new top-level modules under `glados_pycromanager/` if they're meant to be runnable directly.

### Logging

`utils.set_up_logger()` writes log files into the AppData directory. Both stdlib `logging` and `loguru` are used; prefer `logging` for consistency with existing code.

## Documentation

User-facing docs live at `glados_pycromanager/Documentation/UserManual.md` (the README's link to a `glados-pycromanager/glados_pycromanager/Documentation/...` path is stale — the outer `glados-pycromanager/` directory does not exist). Images are in `glados_pycromanager/Documentation/Images/`.
