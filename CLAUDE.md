# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Glados-pycromanager: a Napari-based UI for Pycromanager (python-Micromanager) plus a node-graph framework for autonomous microscopy. Runs either standalone (own QApplication) or as a Napari plugin.

## Environment & install

- Python 3.13 is required (`pyproject.toml`, `environment.yaml`). The user manual still mentions 3.10 — that is outdated; do not follow it.
- One-shot Windows setup: run `win_create_env.bat`. It creates a conda env named `GladosEnv` from `environment.yaml`, then `uv pip install -e .` for editable install.
- The dependency pin set in `pyproject.toml` is strict (numpy/pandas/scipy/napari/pyqt5/tensorflow all hard-pinned). Avoid casually bumping them; the GUI is sensitive to napari/PyQt5 versions.

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

A small pytest suite lives in `tests/`. Run it with:

```
pytest
```

(`pytest` is in `[project.optional-dependencies].dev`; install with `pip install -e ".[dev]"`.) Coverage is currently limited to pure-logic surfaces — backend detection on `MicroscopeInterfaceLayer`, the `java_arr_to_numpy` helper, and the `HelperFunctions` string builders. There is no GUI / hardware integration test.

`Test.py` and `test.ipynb` at the repo root are unrelated scratch files (DIPlib FFT benchmark, etc.), not part of the suite. There is no lint config.

## Architecture

### Backends — `Core/microscopeInterfaceLayer.py` (MIL)

`MicroscopeInterfaceLayer` is the abstraction over three mutually exclusive backends, identified via the `MicroscopeInstance` enum: `PYCROMANAGER_JAVA`, `PYCROMANAGER_PYTHON`, `MMCORE_PLUS`. Code that needs to talk to the microscope should go through `MIL`, branching on `mil.get_microscope_interface()` (alias `MI()` / `get_MI()`). The user picks the backend in the headless start dialog (`headlessGUI` in `GUI_napari.py`) — this writes `shared_data.config.micromanager_config.headless_backend`.

**Backend choice and throughput:** `PYCROMANAGER_JAVA` crosses a Java↔Python bridge (Py4J/PyJavaZ) for every call and every live-mode frame reaching `image_process_fn` — documented by Pycromanager as capped around ~100 MB/s, and this codebase independently measured ~257ms for an uncached Java-bridge round trip (see the `get_exposure`/`get_pixel_size_um` caching in `microscopeInterfaceLayer.py`). `PYCROMANAGER_PYTHON` and `MMCORE_PLUS` both bind straight to MMCore (no Java/bridge hop) and are the faster choice when live frame rate matters most; prefer `PYCROMANAGER_JAVA` only when a feature specifically requires the Java Micro-Manager engine. Note `max_memory_mb` (headless-server memory cap) is not settable on `MMCORE_PLUS` — only `buffer_mb` (circular buffer footprint) applies there; `GUI_napari.py` logs a warning when this backend is selected.

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

**Node kwarg widgets and the Value/Variable/Advanced switch:** how a node's
`__function_metadata__()` kwargs turn into parameter-panel widgets, how the
per-kwarg Value/Variable/Advanced switch (`name@Origin` / `{name@Origin}`
syntax) is wired, and how to add a new typed widget (e.g. the `QCheckBox` used
for `"type": bool` kwargs) without breaking that switch, is documented in
`glados_pycromanager/Documentation/rt_analysis_parameters.md`. Read it before
touching kwarg-widget code in `GUI/utils.py`.

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

User-facing docs live at `glados_pycromanager/Documentation/UserManual.md`; the developer overview is at `glados_pycromanager/Documentation/index.html`. Images are in `glados_pycromanager/Documentation/Images/`.

### Keep this file current

Whenever you explore code in this repo and find a module, pattern, or behavior that isn't captured above, add a concise note to the relevant section here (or a new section if none fits) before finishing the task — don't wait to be asked. This applies any time it happens, not just during the optimization plan. Keep additions terse and factual (what/where/why-it-matters), matching the style already used above; prefer extending an existing bullet over adding a new subsection when the topic already has a home. The goal is for each session to leave this file slightly more complete than it found it, so future sessions ramp up faster.

## Optimization plan & "continue" protocol

There is a long-form optimization roadmap at `claude_project.md`. It defines a
multi-phase plan that runs on a dedicated branch named `claude_optimization`
(already created — make sure you are on that branch before touching code),
with small atomic commits per step.

Three companion files live alongside it:

- **`claude_issues.md`** — inbox for bugs/regressions/follow-ups that must
  be fixed *before* further plan progress. Empty checklist is fine until
  issues appear.
- **`claude_decisions.md`** — append-only log of design and process decisions
  taken while executing the plan. Whenever you make a non-trivial choice
  (which option to pick, what to skip, what to defer), record it there in
  the documented format. This is the place to look when answering "why was
  it done this way?" in a future session.
- **`claude_project.md`** — the plan itself.

When the user says **"continue"** (or any equivalent like "keep going",
"resume", "next step"), follow this protocol exactly:

1. **Confirm you are on `claude_optimization`.** If not, `git checkout
   claude_optimization`. Never commit plan work to another branch.
2. **Read `claude_issues.md` first.** If it contains any unresolved issues
   (typically as a checklist of `- [ ] ...` items), fix those one by one,
   each in its own commit on the `claude_optimization` branch. Mark items
   `- [x]` as you resolve them and move them under `## Resolved (history)`.
   Do not proceed to step 3 until the open list is empty.
3. **Then advance the plan.** Look at the most recent commit on
   `claude_optimization` and pick up at the next un-committed step from the
   Actionables section of `claude_project.md`. Execute exactly that step in
   a single small commit. Do not skip ahead.
4. **Record decisions.** When you make a non-trivial choice while executing
   a step (skip an item, pick option A over B, defer something), add an
   entry to `claude_decisions.md` in the same commit.
5. **Stop at the next phase verification gate** and wait for the user's
   confirmation before starting the next phase.
6. If `claude_project.md` does not exist, or the branch does not exist, ask
   the user before re-creating them.
7. Every commit message follows conventional-commits style (`feat:`, `fix:`,
   `refactor:`, `perf:`, `test:`, `docs:`, `chore:`, `tool:`, `ci:`,
   `style:`, `reliability:`, `security:`, `release:`, `ux:`, `build:`).

Do not run the optimization plan unprompted — it only kicks off on
"continue" (or an explicit instruction).
