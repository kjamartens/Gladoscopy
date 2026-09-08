# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Glados-pycromanager: a Napari-based UI for Pycromanager (python-Micromanager) plus a node-graph framework for autonomous microscopy. Runs either standalone (own QApplication) or as a Napari plugin.

## Environment & install

- Python 3.13 is required (`pyproject.toml`, `environment.yaml`). The user manual still mentions 3.10 — that is outdated; do not follow it.
- One-shot Windows setup: run `win_create_env.bat`. It creates a conda env named `GladosEnv` from `environment.yaml`, then `uv pip install -e .` for editable install.
- The dependency pin set in `pyproject.toml` is strict (numpy/pandas/scipy/napari/pyqt5/tensorflow all hard-pinned). Avoid casually bumping them; the GUI is sensitive to napari/PyQt5 versions.
- `make dev`/`install`/`build` use `uv` (see `Makefile`'s `PIP`/`_ENSURE_UV`), not plain `pip`. Two gotchas that bit this repo once already: (1) `uv pip install` auto-detects its target env and, with a conda env active (`CONDA_PREFIX` set), can prefer that over `.venv/` — so `PIP` always passes `--python .venv/Scripts/python.exe` (Windows) / `.venv/bin/python` (Unix) explicitly rather than relying on auto-detection. (2) `.venv` is tracked via the real `.venv/pyvenv.cfg` file, not the bare directory — a `make clean` that can't fully remove `.venv` (locked `python.exe` from a still-running process/AV scan) leaves a corrupt skeleton that a directory-only Make target would treat as "already built"; `clean` also now fails loudly (reports unremoved paths) instead of silently swallowing `rmtree` errors.

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

(`pytest` is in `[project.optional-dependencies].dev`; install with `pip install -e ".[dev]"`.) Coverage is currently limited to pure-logic surfaces — backend detection and the hardware lock on `MicroscopeInterfaceLayer`, the `java_arr_to_numpy` helper, and the `HelperFunctions` string builders. There is no GUI / hardware integration test.

Seven tests spawn a real `multiprocessing` worker and account for ~80s of the suite's ~140s wall time on Windows (inherent `spawn` re-import cost). They carry the `slow` marker, so `pytest -m "not slow"` runs the other 345 in ~60s; plain `pytest` still runs everything. Two gotchas if you touch them: (1) a test whose spawned child dies must poll `proc.is_alive()` rather than waiting out a queue timeout, or a crash costs the full timeout in dead waiting (`_get_or_fail_fast` in `test_analysis_process.py`); (2) `pytest.importorskip("diplib")` is **not** enough — once an earlier test has pulled IPython into `sys.modules` (napari does), `import diplib` raises `AttributeError`, which `importorskip` does not catch, so the test fails in a full-suite run while passing in isolation. Apply the documented `import IPython.terminal.pt_inputhooks` guard first.

Note the `Real_Time_Analysis` node kwarg dicts hand-built in tests (`rt_analysis_info`) must carry one `LineEdit#<function>#<kwarg>` entry **per kwarg** in the node's `__function_metadata__`: `getEvalTextFromGUIFunction` indexes `methodKwargValues` positionally, so a missing kwarg is an `IndexError` in the child, not a default-value fallback. Bool kwargs use the same `LineEdit#` objectName and are stored as `"True"`/`"False"` strings.

`Test.py` and `test.ipynb` at the repo root are unrelated scratch files (DIPlib FFT benchmark, etc.), not part of the suite. There is no lint config.

## Architecture

### Threading model

Three invariants. They are not currently upheld everywhere — `claude_throughput_project.md`
is the standalone plan that enforces them — but new code must follow them.

- **The Qt/GUI thread is holy.** It paints, lays out, and handles input. It must not touch
  hardware, block on I/O, or run analysis. Anything else belongs on a worker. Violations
  that still exist: `MMcontrols.py` snaps images and moves stages directly in slots,
  `LaserControlScripts.py` writes serial commands to a TriggerScope per keystroke, the log
  widget re-reads the whole log file every ~500 ms, and `NodeItem.paint()` loads a PNG from
  disk on every repaint.
- **All microscope access goes through one owner.** `MILcore`/`core` must have a single
  owning thread; other threads submit requests. Unsynchronized cross-thread `core.*` calls
  are not theoretical: commit `cd01032` fixed a **native access violation / JVM fatal
  crash** caused by two threads driving the same `core.mda`/`Acquisition` object. Note that
  on the Java backend `pyjavaz`'s `Bridge.send_and_receive` already holds a single global
  `_communication_lock` for each round trip, so all bridge traffic is serialized regardless
  of caller — at the measured ~257 ms/call, a GUI-thread hardware call directly steals
  bandwidth from the frame path. `PYCROMANAGER_PYTHON` and `MMCORE_PLUS` have no such lock.
  **As of T-B1 this is enforced at the MIL level:** `MicroscopeInterfaceLayer` holds a
  per-instance `threading.RLock` (`_hw_lock`) and applies it via the `@_hardware_locked`
  decorator to every public method that touches `self.core` (43 of them). Re-entrant
  because MIL methods compose (`get_image_width()` → `get_roi()`), and deliberately
  untimed — a deadlock should be diagnosed, not skipped. `get_exposure` /
  `get_pixel_size_um` are the two exceptions: their cache-hit fast path returns *before*
  acquiring the lock (double-checked inside), so the per-frame display gate never
  serializes behind a slow stage move. `create_mda` is unlocked too — it is pure event-list
  construction and never touches the core. Tests: `tests/test_mil_hardware_lock.py`.
  Single-owner-thread dispatch (`MicroscopeService`) is still T-B3, not yet done.
- **Only the GUI thread touches napari.** Workers emit Qt signals to a GUI-thread receiver;
  they never mutate `viewer.layers` or `viewer.dims` directly. `AnalysisClass.py`'s
  `_do_visualise` signal into `_visualise_on_main_thread` is the reference pattern.
  `autonomous/executor.py` and `utils.forceReset` currently violate this from pool threads.

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
  - **Live/MDA stop→start race guard:** `napariHandler_liveMode`/`napariHandler_mdaMode` are constructed once per session and reused for every toggle, so rapid Live/MDA on-off-on toggling could previously start a new `run_MILCoreAcquisition_worker` (QThreadPool job) while the old one was still tearing down the same `core.mda`/`Acquisition` object (`stop_sequence_acquisition()` is fire-and-forget) — two threads driving the same native MMCore/Java engine concurrently, causing native access violations under stress testing. `napariHandler` now has `_acq_transition_lock` (an `RLock`, since the worker's own cleanup re-enters `acqModeChanged` from its own thread) and `_worker_stopped_event`: `acqModeChanged`'s ON path waits (`ACQ_STOP_TIMEOUT_S`, default 10s) for the previous worker to fully exit before starting a new one, refusing to start (and reverting the mode flag) rather than racing if the timeout is hit.
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

RT-analysis nodes that opt into subprocess isolation (`"__runInSubprocess__": True`, see `AnalysisProcess_customFunction` in `GUI/AnalysisClass.py`) run in a `multiprocessing` `spawn`ed child process with its own, separately-initialized root logger — `set_up_logger()`/`set_log_level()` in the main process cannot reach it. The child is given the Adv.-settings log level at spawn time (`log_level` kwarg into `_subprocess_analysis_worker`, applied via `logging.basicConfig`); a later change to the Adv. settings while such a node is running is pushed live through the same `control_in_queue` used for Performance Mode profiling (`__set_log_level__:<LEVEL>` sentinel, sent via `AnalysisProcess_customFunction.update_log_level()`, called from every entry in `shared_data.RTAnalysisQueuesThreads` in `utils.py`'s advanced-settings save handler).

**Subprocess-isolated RT-analysis startup speedups** (fixes a ~20s per-start cost reported for e.g. FFT): a cold `spawn` pays for re-importing the whole `Real_Time_Analysis` package tree plus whatever heavy library the node needs (diplib, tensorflow/stardist, …), and — separately — `AnalysisProcess_customFunction.__init__` used to synchronously build a visualisation "shadow" object on the *GUI thread* via `utils.realTimeAnalysis_init(...)`, freezing the UI for however long that model/weight load took. Two mechanisms now cut this down:

- `GUI/subprocess_pool.py`'s `WarmSubprocessPool` pre-spawns one blank child at app startup (`shared_data._rt_subprocess_pool.start()`, called right after `Shared_data()` in `GUI_napari.py`'s `main()`) that pre-imports the package tree and (best-effort, since it's the only node opted in today) `diplib`, then idles waiting to be handed a real node's `analysisInfo`/queues — shortcutting the first-ever subprocess-node start in a session. Extend its pre-imported-library list (or generalize via an optional `"__prewarm_imports__"` metadata key) if more nodes opt into `__runInSubprocess__`.
- `shared_data._rt_subprocess_cache` (a dict keyed by `AnalysisClass._rt_config_key(analysisInfo)`, a stable hash of the node's config) lets `stop()`/`destroy()` park a still-alive, already-warmed-up worker (+ its visualisation shadow object) instead of killing it — `_park_subprocess_worker` handles the cap/idle-timeout eviction opportunistically on each park, no dedicated QTimer needed. A later `__init__` with the identical config reclaims it directly (`_worker_warmed_up = True` immediately, no spawn/import/model-load). Trade-off: a node's Python-level state (e.g. a counter set on `self` in `run()`) now survives a stop→restart of the same config instead of getting a fresh instance — undocumented per-node reset behavior would need a reset hook if this ever matters (see the class docstring's "v1 limitations"). `AnalysisClass.terminate_all_rt_subprocesses()` is wired into `GUI_napari.py`'s `aboutToQuit` (before the forced `os._exit(0)`) so parked/warm processes don't get orphaned.

**diplib import gotcha in `spawn`ed subprocesses (IPython inputhook):** if `'IPython'` is already in `sys.modules` in a subprocess (e.g. the app was launched from an IPython/Jupyter shell, or another import pulled IPython in) but `IPython.terminal.pt_inputhooks` hasn't itself been imported yet, `import diplib` raises `AttributeError: module 'IPython.terminal' has no attribute 'pt_inputhooks'` — modern IPython (9.x) only sets `pt_inputhooks` as an attribute of `IPython.terminal` once that submodule has actually been imported, but `diplib/viewer.py` (`from . import viewer` inside `diplib/__init__.py`) assumes it's already there whenever `'IPython' in sys.modules`. Both `subprocess_pool.py`'s pre-warm bootstrap and `FFT_im.py`'s `RealTimeFFT.__init__` work around it by doing `import IPython.terminal.pt_inputhooks` first when `'IPython' in sys.modules`, before `import diplib`. Apply the same guard to any new node that imports diplib in a subprocess-isolated context.

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
- **`claude_throughput_project.md`** — a *separate*, standalone plan targeting live/MDA
  data throughput and the threading invariants above. It has its own operating protocol
  and its own 51-task checklist; it is **not** advanced by "continue". Run it only when
  the user asks for it by name (e.g. "work on claude_throughput_project.md"). It shares
  the `claude_optimization` branch and logs to `claude_decisions.md` / `claude_issues.md`
  like the main roadmap.

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
