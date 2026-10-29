# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Glados-pycromanager: a Napari-based UI for Pycromanager (python-Micromanager) plus a node-graph framework for autonomous microscopy. Runs either standalone (own QApplication) or as a Napari plugin.

## Environment & install

- Python 3.13 is required (`pyproject.toml`). Installs are **uv + `.venv` only** (conda support was dropped 2026-10-20: `environment.yaml`, `win_create_env.bat` and `make env` are gone).
- End-user Windows setup: `install_windows.bat` (needs git + uv; offers to install uv; `/y` = unattended). It runs `uv venv --python 3.13 --seed .venv`, `uv pip install --compile-bytecode -e .`, the `install_check` stamp and `shortcuts install`. It must stay **CRLF** (`.gitattributes`): cmd mis-parses labels/`goto` in LF batch files.
- **uv's Python + PyQt5 + pymmcore: load order of `msvcp140.dll`.** PyQt5 bundles an old `MSVCP140.dll` (`PyQt5/Qt5/bin`); if Qt is imported before pymmcore, every later module gets that copy and `pymmcore.CMMCore()` is an access violation. A conda-based Python (the old `.venv`s were built on miniconda 3.13.5) masks it with its own newer `MSVCP140.dll`; uv's python-build-standalone ships none, so on a uv `.venv` the test suite crashed (`test_recipe_stage_devices_real_core.py`), and with pymmcore 12.5.1 so did every GUI launch (in `loadSystemConfiguration`): the `glados_pycromanager.GUI` import chain loads Qt before `startup.py`'s early `import pymmcore` can help. `glados_pycromanager/__init__.py` now calls `win_runtime.preload_system_msvcp140()` (loads `System32\msvcp140.dll` unless some msvcp140 is already loaded) and `tests/conftest.py` imports the package first. A path where something else imports Qt *before* `glados_pycromanager` (napari launching the plugin) is not covered; it only uses the Java `Core()`, not `CMMCore`. Tests: `tests/test_win_runtime.py` (only a uv interpreter can actually fail it).
- On Windows the Makefile uses `uv` from PATH when `uv --version` answers (`_UV_ON_PATH`), else falls back to `python -m uv` bootstrapped into the PATH `python` — so `make dev` works on a machine with only git + uv + make.
- Clean-room install check (no VM/Sandbox on the dev laptop): fresh `git init` copy of the tree, PATH = Windows + Git + a copied `uv.exe`, cold `UV_CACHE_DIR`, `UV_PYTHON_PREFERENCE=only-managed`, `APPDATA` redirected (shortcuts). The Claude harness sets `NoDefaultCurrentDirectoryInExePath=1`, so cmd will not run a bare `install_windows.bat` from the cwd there — clear it or use `.\`.
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
- `make run-demo-smlm` launches straight into a fixed local demo backend with no start
  dialog — same `--backend/--config/--mm-path/--buffer-mb/--max-memory-mb` override path
  as `make run-mm`, but the values come from **`demo_settings.mk`** (`-include`d by the
  `Makefile`; `DEMO_*` vars, all `?=` so `make run-demo-smlm DEMO_BUFFER_MB=1024` still
  wins). Edit that file, not the recipe. It is per-machine and git-ignored: copy the
  tracked `demo_settings.mk.example` (which the tests read) to create it. `make run-demo` is unrelated and unchanged: it
  is `--auto-demo`, the pymmcore-plus *bundled* install + `MMConfig_demo.cfg`, and is what
  `docs/plans/claude_throughput_project.md`'s verification steps mean. Every CLI-override launch now
  logs one INFO line naming the backend, install path, config and both memory settings.
  Tests: `tests/test_demo_settings_makefile.py`.
- **Makefile gotcha (fixed twice):** GNU make on Windows uses `sh.exe` as the recipe
  shell whenever one is on PATH (Git Bash, scoop, MSYS) *even when started from
  PowerShell or cmd*, and cmd.exe otherwise — but `$(SHELL)` reads `sh.exe` in **both**
  cases. sh reads the `\S` in `.venv\Scripts\python.exe` as an escape; cmd parses an
  unquoted `.venv/Scripts/python.exe` as `.venv` + a `/Scripts` switch. The first fix
  keyed the separator on `$(SHELL)` (`_WINPATH`), which always chose forward slashes
  and broke `make dev` wherever no sh is on PATH (a stock Git for Windows install only
  adds `git\cmd`; found by the 2026-10-20 clean-room install). `PYTHON` is now the
  **quoted** forward-slash path, which both shells run. Tests:
  `tests/test_demo_settings_makefile.py` (runs it in real cmd and sh).

A small pytest suite lives in `tests/`. Run it with:

```
pytest
```

(`pytest` is in `[project.optional-dependencies].dev`; install with `pip install -e ".[dev]"`.) Tests need no hardware: they use mocks, offscreen Qt widgets, and pymmcore-plus' bundled demo camera for real-core MDA tests. There is no test against real hardware or a full GUI session.

Seven tests spawn a real `multiprocessing` worker and account for ~80s of the suite's ~140s wall time on Windows (inherent `spawn` re-import cost). They carry the `slow` marker, so `pytest -m "not slow"` runs the other 345 in ~60s; plain `pytest` still runs everything. Two gotchas if you touch them: (1) a test whose spawned child dies must poll `proc.is_alive()` rather than waiting out a queue timeout, or a crash costs the full timeout in dead waiting (`_get_or_fail_fast` in `test_analysis_process.py`); (2) `pytest.importorskip("diplib")` is **not** enough — once an earlier test has pulled IPython into `sys.modules` (napari does), `import diplib` raises `AttributeError`, which `importorskip` does not catch, so the test fails in a full-suite run while passing in isolation. Apply the documented `import IPython.terminal.pt_inputhooks` guard first.

A test that builds a real `CMMCorePlus` and waits on its MDA events must use the
`direct_mmcore_signals` fixture (`tests/conftest.py`, sets `PYMM_SIGNALS_BACKEND=psygnal`).
pymmcore-plus switches to Qt signals whenever a QApplication exists. Any earlier `qapp`
test leaves one behind, and with no event loop running, `frameReady` is then never
delivered. The test then fails only in a full-suite run.

Note the `Real_Time_Analysis` node kwarg dicts hand-built in tests (`rt_analysis_info`) must carry one `LineEdit#<function>#<kwarg>` entry **per kwarg** in the node's `__function_metadata__`: `getEvalTextFromGUIFunction` indexes `methodKwargValues` positionally, so a missing kwarg is an `IndexError` in the child, not a default-value fallback. Bool kwargs use the same `LineEdit#` objectName and are stored as `"True"`/`"False"` strings.

`Test.py` and `test.ipynb` at the repo root are unrelated scratch files (DIPlib FFT benchmark, etc.), not part of the suite. There is no lint config.

## Architecture

### Threading model

Three invariants. New code must follow them. They were enforced by the (completed,
archived) throughput plan, `docs/plans/claude_throughput_project.md`, whose task IDs
(T-B3, T-F9, …) the notes below refer to.

- **The Qt/GUI thread is holy.** It paints, lays out, and handles input. It must not touch
  hardware, block on I/O, or run analysis. Anything else belongs on a worker. Tier F of
  the throughput plan removed the standing violations; see *GUI-thread work removed in
  Tier F* below. T-B4 moved the hardware slots onto the T-B3 owner thread (the
  site-specific laser UI it also covered, `LaserControlScripts.py`, was deleted in
  2026-10). **`FlowChart_dockWidgets`**: `updateCoreVariables` (which the plan
  anchored under its old name `createCoreVariables`) runs on every node finish in
  a recipe and is one hardware read per stage plus one `ConfigInfo` per config
  group; it now collects on the owner thread via `_collectCoreVariables()` and
  swaps the finished dict in with one assignment (`_refreshCoreVariables`), so the
  snapshot is **eventually consistent** — a reader right after a node finishes may
  see the previous one. `createSingleCoreVar` grew a `target=` parameter for that.
  Tests: `tests/test_core_variables_owner_thread.py`. **`MMcontrols.py` completed
  T-B4**: `submitHardware(shared_data, fn, ...)` / `guiThreadCall(shared_data, fn)`
  at module scope are the pair every slot uses — queue the hardware work, bring the
  widget or napari touch back. Migrated: `snapImage` / `addImageToAlbum` (the snap
  blocks for the whole exposure), the exposure write behind `changeLiveMode`, all
  three shutter slots, `resetROI` / `zoomROI` / `setROI`, both stage moves and every
  position read-back, and the config writes (`set_config`, plus the slider's and
  edit field's shared `_setUnderlyingConfigProperty`). Four things to know:
  - **A read-back submitted right after a move reports the post-move position**,
    because the queue is FIFO within a priority. That is the ordering guarantee the
    stage slots rely on instead of blocking.
  - **`changeLiveMode` flips `liveMode` from the exposure write's completion
    callback**, bounced back to the GUI thread by `guiThreadCall` — the camera must
    not start on the previous exposure, and flipping it *on the owner thread* would
    deadlock (`acqModeChanged` waits for the acquisition worker, whose own stop call
    is queued on that same thread).
  - **`setROI`'s live branch gets its own short-lived thread** for the same reason:
    it stops live, waits, sets, waits and restarts, which belongs on neither the GUI
    thread (up to `ACQ_STOP_TIMEOUT_S`) nor the owner thread. `_setROI_hw` (no live
    mode) is a single queued job. `resetROI` now mirrors this exactly
    (`_resetROI_liveRestart`) — it originally queued `clear_roi()` straight to the
    owner thread with no live-mode check at all, so clicking "Reset ROI" while live
    changed the frame size out from under the running acquisition instead of
    stopping and restarting it. `zoomROI` needed no equivalent fix: it already
    computes the new rect and calls `self.setROI(...)`, so it inherits setROI's
    live handling for free.
  - **The restart must wait for the previous worker's own teardown, not just
    `hw.wait_for_system()`.** All three live-restart helpers
    (`_setROI_liveRestart`, `_resetROI_liveRestart`, `_exposureChange_liveRestart`)
    originally did `liveMode = False; hw.wait_for_system(); <hardware call>;
    hw.wait_for_system(); liveMode = True`. `hw.wait_for_system()` is a
    `MicroscopeProxy` call — it only confirms the *hardware* queue drained, not
    that the acquisition worker's Python thread (`run_MILCoreAcquisition_worker`)
    has finished draining the frame ring, finishing any NDTiff archive and
    disconnecting the visualisation worker's `yielded` signal, which happens in
    that thread's own `finally` (where `_worker_stopped_event` finally gets set).
    Restarting before that finishes raced `acqModeChanged`'s *own* internal wait
    for the same event on the ON path: when that wait timed out it reverted by
    setting `liveMode = False` again, re-entering `stopLiveModeVisualisation` and
    disconnecting a signal the first, genuine stop had already disconnected —
    `TypeError: disconnect() failed between 'yielded' and all its connections`,
    observed in practice on a real acquisition (dozens of frames in flight,
    several seconds to tear down — nothing like the near-instant
    `wait_for_system()` return). `waitForLiveModeWorkerStopped(shared_data,
    label)` (module scope, next to `submitHardware`/`guiThreadCall`) is the fix:
    it waits on `shared_data._livemodeNapariHandler._worker_stopped_event` with
    `ACQ_STOP_TIMEOUT_S`, replacing the first `hw.wait_for_system()` in each
    helper, and on timeout logs an error and **skips the hardware change and the
    restart** — attempting one anyway would just re-race the same timeout.
    Tests: `tests/test_mmcontrols_owner_thread.py::test_set_roi_waits_for_worker_teardown_before_restarting`,
    `::test_set_roi_restarts_once_the_worker_confirms_it_stopped`.
  - **`drawROI` no longer pauses live mode to read the sensor size** — that was a
    stop / read / 0.2 s GUI-thread sleep / restart around a pure query. It is one
    proxy read now, and the only call in the file the GUI thread still waits on
    (it needs the bound before installing the drag callbacks).
  Still inline, deliberately: pure reads on click-only paths — `updateShutterOptions`,
  the scanning/grid helpers' `get_pixel_size_um`/`get_roi`, and `ConfigInfo`'s
  introspection (which runs at panel construction). Tests:
  `tests/test_mmcontrols_owner_thread.py`.
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
  decorator to every public method that touches `self.core` (64 applications as of 2026-10-13). Re-entrant
  because MIL methods compose (`get_image_width()` → `get_roi()`), and deliberately
  untimed — a deadlock should be diagnosed, not skipped. `get_exposure` /
  `get_pixel_size_um` are the two exceptions: their cache-hit fast path returns *before*
  acquiring the lock (double-checked inside), so the per-frame display gate never
  serializes behind a slow stage move. `create_mda` is unlocked too — it is pure event-list
  construction and never touches the core. Tests: `tests/test_mil_hardware_lock.py`.
  **As of T-B3 there is a single owner thread**, `Core/microscope_service.py`'s
  `MicroscopeService`: a `QObject` owning one MIL, running every call to it on its
  own daemon thread, ordered by a `PriorityQueue` (`Priority.FRAME` <
  `Priority.NORMAL` < `Priority.LOW`). Started once per session by
  `Shared_data.start_microscope_service()` (called from `GUI_napari.main()` right
  after the backend selection settles, stopped on `aboutToQuit` before the
  `os._exit(0)`), reachable as `shared_data.microscope_service` and
  `shared_data.microscope_proxy(priority)`. Three things to know:
  - **`MicroscopeProxy` keeps MIL's synchronous API** and blocks *the caller's*
    thread on the reply, so worker and node code needs no rewrite. Non-callable
    attributes (`core`, `mda`, the caches) fall through to the real MIL. With no
    service running it calls MIL directly instead of raising, which is what keeps
    the tests, the napari-plugin path and post-shutdown callers working.
  - **Re-entrancy is inline, not queued.** `submit`/`call` from the owner thread
    execute immediately — MIL methods compose and the streaming loop calls back in,
    so anything else would deadlock.
  - **Streaming mode is why the frame path gains no hop.** `start_streaming(pull_once)`
    makes the live pull loop (T-C3) the service loop body, so the thread that owns
    the hardware is the thread that pulls the frames;
    `run_liveSequence_worker` then only waits on the stop flag
    (`LIVE_SEQUENCE_STOP_POLL_S`) and falls back to its own in-worker loop when no
    service is running. Between two pulls the loop still drains up to
    `STREAM_REQUEST_BUDGET` (8) queued requests, so a stage move issued during live
    mode is serviced within a frame or two instead of waiting out the acquisition.
  It is deliberately **not** a `QThread` running `exec_()` — nothing on the owner
  thread needs a Qt event loop, and a plain daemon thread matches `FrameRing`'s
  consumer and `ZarrFrameWriter`. It stays a `QObject` so `request_completed`
  reaches GUI slots as a queued signal (T-B4). `note_gui_block()` logs a warning
  once per method when a GUI-thread caller blocks on a reply, making the
  not-yet-migrated slots visible. T-B1's `_hw_lock` remains and is what makes the
  still-direct callers safe. Tests: `tests/test_microscope_service.py`,
  `tests/test_live_sequence_worker.py`.
- **The display path never calls MIL (T-B2).** `Shared_data` mirrors the hardware
  constants the display needs into plain attributes — `hw_exposure_ms`,
  `hw_pixel_size_um`, `hw_roi`, `hw_image_shape` — and
  `napariGlados._mirrored_exposure_ms` / `_mirrored_pixel_size_um` /
  `_apply_pixel_scale` read those instead of `shared_data.MILcore.*`.
  `napariUpdateLive`'s rate-limit gate made a `get_exposure()` call per candidate
  frame on the GUI thread, and each layer creation three `get_pixel_size_um()`
  calls. The mirror is refreshed *only* where the value can change: MIL invokes a
  registered callback (`MIL.set_hardware_mirror`, called from `Shared_data`'s
  `MILcore` property setter) at the end of `set_core`, `set_exposure`, `set_roi`
  and `clear_roi` with a reason string, and `run_MILCoreAcquisition_worker`
  calls `refresh_hardware_mirror()` once at acquisition start. `None` means "not
  read yet" — the helpers then refresh once and fall back to MIL, so a
  `shared_data` that never bound a MIL mirror still works. The callback runs on
  the calling thread inside the (re-entrant) `_hw_lock`, so it may read MIL back;
  an exception in it is logged, never propagated into the hardware write.
  Note the pixel-size mirror inherits `get_pixel_size_um`'s cache semantics —
  only a `set_core` re-reads it, so an objective change through a config group
  is not picked up (pre-existing; same for the MIL cache itself). Tests:
  `tests/test_hardware_mirror.py`.
- **Only the GUI thread touches napari.** Workers emit Qt signals to a GUI-thread receiver;
  they never mutate `viewer.layers` or `viewer.dims` directly. `AnalysisClass.py`'s
  `_do_visualise` signal into `_visualise_on_main_thread` is the original reference
  pattern. **As of T-F9 there is a general one:** `GUI/napari_bridge.py`'s `NapariBridge`,
  reached via `get_bridge(shared_data)` (cached on `shared_data._napari_bridge`). It is a
  `QObject` that takes GUI-thread affinity in `__init__` *itself* — `moveToThread(app.thread())`
  — so it does not matter which thread constructs it; without that, a bridge first created
  by a worker would carry that thread's affinity and every "queued" call would target a
  thread with no event loop, failing silently. `submit(fn, wait=False)` fires and forgets;
  `wait=True` blocks the *worker* (never the GUI thread, which runs inline) with a timeout
  and hands back the result or re-raises the exception. Prefer `replace_layer` over
  `remove_layer` + `add_layer`: one GUI-thread call leaves no window in which the layer
  list has neither. Migrated in T-F9: `autonomous/executor.py` (both RT-visualisation
  blocks, via `_replace_visualisation_layer`), `utils.forceReset_actual`'s two mode flips
  (the bare assignment re-entered `acqModeChanged` off-thread), and
  `napariHandler.acqModeChanged`'s two `moveLayerToTop` calls (via `self._napari_bridge()`).
  Tests: `tests/test_napari_bridge.py`.

### Backends — `Core/microscopeInterfaceLayer.py` (MIL)

`MicroscopeInterfaceLayer` is the abstraction over three mutually exclusive backends, identified via the `MicroscopeInstance` enum: `PYCROMANAGER_JAVA`, `PYCROMANAGER_PYTHON`, `MMCORE_PLUS`. Code that needs to talk to the microscope should go through `MIL`, branching on `mil.get_microscope_interface()` (alias `MI()` / `get_MI()`). The user picks the backend in the headless start dialog (`headlessGUI` in `GUI_napari.py`) — this writes `shared_data.config.micromanager_config.headless_backend`.

**Backend choice and throughput:** `PYCROMANAGER_JAVA` crosses a Java↔Python bridge (Py4J/PyJavaZ) for every call and every live-mode frame reaching `image_process_fn` — documented by Pycromanager as capped around ~100 MB/s, and this codebase independently measured ~257ms for an uncached Java-bridge round trip (see the `get_exposure`/`get_pixel_size_um` caching in `microscopeInterfaceLayer.py`). `PYCROMANAGER_PYTHON` and `MMCORE_PLUS` both bind straight to MMCore (no Java/bridge hop) and are the faster choice when live frame rate matters most; prefer `PYCROMANAGER_JAVA` only when a feature specifically requires the Java Micro-Manager engine. Note `max_memory_mb` (headless-server memory cap) is not settable on `MMCORE_PLUS` — only `buffer_mb` (circular buffer footprint) applies there; `GUI_napari.py` logs a warning when this backend is selected.

**`MMCORE_PLUS` MDA runs register a resilient `MDAEngine` (`GUI_napari.py`'s
`register_resilient_mmcore_mda_engine`, called right after both
`CMMCorePlus(...)` construction sites).** pymmcore-plus's default
`MDAEngine.timeout_action` is `"raise"`: for a hardware-sequenced (buffered,
triggered) camera burst — one per z-step whenever `time_plan.interval == 0`
groups several events together — a burst that delivers zero frames within
`timeout_first_frame` (default 20s) raises `TimeoutError` out of the runner
thread and **aborts the entire MDA on the spot**, discarding every event still
to come even though everything acquired so far saved fine. A burst that drops
only *some* of its expected frames is already non-fatal on its own (logged as
"Unexpected number of images returned from sequence... Expected N, got M");
it's a *complete* stall on one event that used to be fatal. The registered
engine sets `timeout_action="warn"` (log and move on to the next event, same
missing-frame handling as a partial-count burst) and raises
`timeout_first_frame` from 20s to 60s, since a busy serial/USB bus (many
devices in this rig are driven by round-trip serial commands, see the T-B4
laser-controls note above) can plausibly delay a stage move + trigger past
20s without the acquisition actually being stuck. This alone is a resilience
stopgap, not a fix — it stops one stalled event from killing the whole run,
but does not stop frames from being dropped in the first place.

**Root cause identified for the z-step case: a free-running external trigger
generator racing the camera's per-burst re-arm.** `setup_event()` calls
`core.waitForSystem()` *before* the camera is armed for the next sequenced
burst — so between one z-step's burst ending and the next one's
`startSequenceAcquisition()` call, the camera is completely deaf while the Z
stage moves and settles. A trigger generator with a fixed cadence and no
awareness of camera-armed state keeps firing through that gap regardless, and
any pulse landing in it is lost forever (not delayed, not buffered) — one gap
per z-step, so an N-z-step MDA has N chances to fall out of sync, which is
exactly why a pure time-series (no z, one continuous burst, one arm, zero
gaps) worked perfectly on the same rig while a z-stack did not.
`MDAConfig.mmcore_wait_for_z_settle` (hidden, default `'False'`) is the fix
for this specific case: when not `'True'`,
`register_resilient_mmcore_mda_engine` registers
`_build_z_settle_skipping_mda_engine_class()`'s `ZSettleSkippingMDAEngine`
instead of the stock engine, which overrides `setup_event()` to still issue
the Z move (`setup_sequenced_event`/`setup_single_event`) but skip the
trailing `waitForSystem()` for a `SequencedEvent` — the camera is armed
immediately after the move command is issued rather than after the stage
physically settles, closing the deaf window down to the dispatch latency of
issuing the arm call. Non-sequenced (single) events are unaffected and still
wait normally. Trade-off: the leading frame(s) of a burst may be captured
while Z is still in motion (accepted, since a slightly-blurred frame beats a
missing one or an aborted acquisition). Set `mmcore_wait_for_z_settle` to
`'True'` to restore pymmcore-plus' default wait-then-arm behaviour if
positional accuracy ever matters more than trigger sync for a given setup.
If frames still drop with this off, also check the circular buffer size
(`buffer_mb`) and consider testing `use_hardware_sequencing=False` on the
`MDAEngine` to see whether the sequenced (vs. one-shot-per-frame) acquisition
path is itself implicated, or whether the trigger generator can be gated by
the camera/stage's own ready signal instead (the only way to get zero lost
pulses, since no software change can make a truly unsynchronized generator
wait).

**The same fix exists for the `PYCROMANAGER_PYTHON` backend, but not
`PYCROMANAGER_JAVA`.** pycromanager's own pure-Python acquisition engine
(`pycromanager.acquisition.acq_eng_py.internal.engine.Engine`, used by the
headless 'Python' backend) has the identical shape of bug: `start_z_drive()`'s
`move_z_device()` calls `core.wait_for_device(z_stage)` *after* `set_position()`,
before `acquire_images()` arms the camera for the next sequenced burst — one
settle-wait per z-step, same free-running-trigger race. `GUI_napari.py`'s
`register_resilient_pycromanager_python_engine(shared_data)` (called right
after `shared_data.MILcore.set_core(Core())` in both `start_headless(...,
python_backend=True)` call sites) monkeypatches `Engine.start_z_drive` with a
faithful copy that skips the trailing `wait_for_device()` call, gated live by
`MDAConfig.pycromanager_wait_for_z_settle` (hidden, default `'False'`, same
semantics as `mmcore_wait_for_z_settle`) — read fresh off `Engine._glados_shared_data`
on every z-step, so no re-patch is needed when the setting changes, only a
class-attribute update. **`pycromanager` is pulled from git main in
`pyproject.toml` (unpinned)**, so the patch first checks
`inspect.getsource(Engine.start_z_drive)` for the literal markers this patch
was written against and silently keeps the stock wait-then-arm behaviour
(with a warning) if they're missing, rather than risk silently breaking Z
moves against a changed upstream shape. **There is no equivalent for
`PYCROMANAGER_JAVA`**: that backend's engine is AcqEngJ, compiled and running
inside the JVM, unreachable for a Python-level monkeypatch — the Z panel's
"Wait for Z to settle before arming camera" checkbox (`MDAGlados.py`) is
disabled with an explanatory tooltip whenever that backend is active. The
checkbox otherwise reads/writes the backend-appropriate config field
(`_zWaitForSettleConfigValue`) and re-applies the change live via the
matching `register_resilient_*` function on toggle
(`_onZWaitForSettleToggled`) — no app restart needed for either backend.

MIL also exposes the **circular-buffer / continuous-sequence primitives** (T-C1):
`start_continuous_sequence_acquisition(interval_ms=0)`, `is_sequence_running()`,
`get_remaining_image_count()`, `pop_next_image_and_metadata()`,
`get_last_image_and_metadata()`, `clear_circular_buffer()`. These are the
engine-free path a real live mode uses (MM's own live window, napari-micromanager)
— no `MDAEvent`, no per-frame pydantic validation. The two frame-pulling methods
normalise all three backends' return shapes to `(2-D np.ndarray, dict)` via
`_metadata_to_dict()` / `_reshape_if_flat()`; the latter prefers the frame's own
`Height`/`Width` tags and falls back on `_image_shape_cache` (ROI-derived,
invalidated in `set_core`/`set_roi`/`clear_roi`, same idiom as the exposure and
pixel-size caches). The `sequence` live path (T-C3, below) is built on them.

**Device property browser:** MIL exposes full device/property introspection —
`get_loaded_devices()`, `get_device_property_names(device)`,
`get_property(device, prop)` / `set_property(device, prop, value)`,
`is_property_read_only(device, prop)`, `has_property_limits(device, prop)` +
`get_property_lower_limit`/`get_property_upper_limit` for range properties, and
`get_allowed_property_values(device, prop)` for enum properties. All follow the
same three-way snake_case/snake_case/camelCase branch pattern (Java bridge /
pymmcore / pymmcore-plus), with the Java branch wrapped in
`java_arr_to_numpy()` for vector-returning calls. `GUI/device_property_browser.py`'s
`collect_device_properties(mil)` walks all three into a flat list of dicts
(GUI-free, unit-tested against a mocked MIL), and `DevicePropertyBrowserDialog`
renders it as an editable `QTableWidget` (enum → `QComboBox`, ranged → `QLineEdit`,
read-only → greyed out), opened via the "Device Property Browser…" button in
`MMConfigUI`'s debug button row (`GUI/MMcontrols.py`, next to "Adv. settings").
This replaced a dead, single-backend, buggy prototype
(`MMConfigUI.get_device_properties`, formerly in a `#region deprecated` block)
that called raw Java-vector methods directly and silently dropped every
range-limited property (its `has_property_limits` branch never appended to
the results list — only the `enum` branch did). Tests:
`tests/test_mil_device_properties.py`, `tests/test_device_property_browser.py`.

**Config group / preset editor:** MIL also exposes the write side of the same
MMCore config-group API: `define_config_group(group)`, `define_config(group,
preset, device=None, prop=None, value=None)` (device/prop/value all-or-nothing
— omit them to create/keep an empty preset, pass them to add or overwrite one
device/property setting in that preset), `delete_config(group, preset,
device=None, prop=None)` (omit device/prop to delete the whole preset,
otherwise remove just that one setting), `delete_config_group`,
`rename_config(group, old, new)`, `rename_config_group(old, new)`,
`is_config_defined`, and `save_system_configuration(path)` (writes the current
device/config state to a Micro-Manager `.cfg` file — this is a full-state
dump, not a diff). `get_config_settings(config_data)` is the many-setting
counterpart to `get_config_device_label`/`get_config_property_name` (which
only ever look at `getSetting(0)`) — it walks every setting in a preset, which
matters for presets like a "Channel" group that set more than one device at
once. All follow the existing three-way branch pattern.

`GUI/config_group_editor.py` deliberately mirrors Micro-Manager's own
"Configuration settings" panel / Group Editor / Preset editor methodology and
phrasing rather than inventing a new UX: a group is defined *once* by picking
which device properties belong to it (`GroupEditorDialog`, phrased exactly
like MM's "Specify properties in this configuration group:" with device-type
filter checkboxes — cameras/shutters/stages/"wheels, turrets, etc."/other
devices, bucketed via `device_type_bucket()` off `mil.get_device_type()`,
mirroring `MMcontrols.py`'s `getDevicesOfDeviceType` `deviceTypeArray` — plus
a name/property search box and a "Show read-only" toggle); every preset in
that group then just supplies values for that same fixed property set
(`PresetEditorDialog`, titled `Preset editor for the "<group>" configuration
group`). `group_property_set(mil, group)` derives that fixed set as the union
of settings across the group's existing presets, since MMCore has no
independent record of "which properties belong to a group" — only presets.
Interacting with `GroupEditorDialog`'s "Current Property Value" column writes
to the live device immediately (it reuses
`device_property_browser.build_property_value_widget`, extracted from that
module for exactly this sharing), because that's how you put the hardware
into the state a new group's initial `"NewPreset"` preset should capture;
`PresetEditorDialog`'s value column does not touch hardware. Editing an
*existing* group's property selection adds/removes that setting across every
one of its presets (added properties take the live value shown in the
editor). `collect_config_groups(mil)` (GUI-free, unit-tested against a mocked
MIL) feeds the top-level `ConfigGroupEditorDialog` — one row per group with a
preset `QComboBox` (selecting a preset calls `set_config` immediately) and
Group/Preset `+`/`−`/`Edit` buttons opening the two editors above — opened via
the "Config Group Editor…" button next to "Device Property Browser…" in
`MMConfigUI`'s debug button row (`GUI/MMcontrols.py`). "Save" writes via
`save_system_configuration` to `shared_data.config.micromanager_config.config_path`.
This all matches the actual `.cfg` file syntax 1:1 — one
`ConfigGroup,<group>,<preset>,<device>,<property>,<value>` line per setting.
Tests: `tests/test_mil_config_groups.py`, `tests/test_config_group_editor.py`.
`ConfigGroupEditorDialog`'s "Save" button flashes `"Saved!"` (disabled) for
`SAVED_FEEDBACK_MS` (1.5s) after a successful save, reverted by
`_restoreSaveButton()` via `QTimer.singleShot` — otherwise a save has no
visible effect at all. The two "…Browser…"/"…Editor…" buttons and the
"Refresh configs from MM" button now all live together in the live
Configurations panel, not this dialog — see `MMConfigUI` below.

**Configurations panel — `MMConfigUI`/`ConfigInfo` (`GUI/MMcontrols.py`):**
this is the *other*, always-visible config-group UI (one row per group with
a dropdown/slider/input-field, built in `MMConfigUI.__init__`'s
`showConfigs` block) — distinct from the `ConfigGroupEditorDialog` popup
above, which is reached from a button inside this same panel alongside
"Device Property Browser…" and "Refresh configs from MM" (previously these
two buttons sat in the unrelated debug-button row).
- **`ConfigInfo.isDropDown()`/`isSlider()`/`isInputField()` are mutually
  exclusive by construction**: `isDropDown()` is `nrConfigs() > 1` and
  nothing else — a group with a single preset is *never* shown as a
  preset-name dropdown, even if that one preset has a real name (not the
  `'NewPreset'` sentinel); it always goes to `isSlider()`/`isInputField()`
  (branching on `hasPropertyLimits()`) so a single-property group is edited
  through that property's own widget, matching Micro-Manager's own
  behaviour and the Group/Preset editor's methodology above. Previously a
  single *named* preset with a ranged property satisfied both `isDropDown()`
  and `isSlider()`, and `addLabel()` added widgets for both predicates via
  independent `if`s rather than `elif` — producing a stray 1-item dropdown
  glued onto (and crowding out the label next to) the slider/input-field.
  `addLabel()` now uses `elif`.
- **A group is read-only when every property backing it is** — `ConfigInfo.isReadOnly()`
  gets the group's `(device, property)` set via `config_group_editor.group_property_set()`
  (reused, not re-derived) and is `True` iff that set is non-empty and
  `MIL.is_property_read_only()` says so for all of them. There is no separate
  "read only" flag anywhere (MMCore's `.cfg` format has none) — it is purely
  derived at render time, per the `Real_ms`-style status group in
  `DemoSMLM.cfg` (a single preset mapping to a computed property like
  `SMLMDemoCam.General_ActualFrameIntervalMs`) that has nothing a user could
  actually set. `addLabel()` checks `isReadOnly()` *first*, before
  `isDropDown()`/`isSlider()`/`isInputField()`, and renders a plain `QLabel`
  (`addReadOnlyDisplay`) instead; `updateValuefromMM()` refreshes that label's
  text the same way it refreshes the other widget types.
- **The panel can rebuild itself**, via `rebuildConfigLayout()` (clears
  `configLayout` through `_clearConfigLayout()`/`_clearLayoutItem()`,
  re-fetches `get_available_config_groups()` from MIL, and reconstructs
  `self.config_groups` + every row from scratch). The previous mechanism
  (`updateConfigsFromMM()`, since removed) only pushed new
  *values* into already-existing row widgets — a dropdown's item list and
  the row count itself were frozen at construction, so a group added,
  renamed, or given a new preset via the config group editor could never
  appear, and refreshing an existing dropdown to a preset name that didn't
  exist yet at construction silently did nothing (`QComboBox.setCurrentText`
  on a non-matching string is a no-op). The "Refresh configs from MM"
  button, `updateAllMMinfo()`, and `openConfigGroupEditor()`'s post-dialog
  refresh all now call `rebuildConfigLayout()`. Because a rebuild (also the
  periodic auto-refresh tick) recreates every dropdown, **`addDropDown` itself
  selects MM's current preset** via `_selectDropDownPreset` (signals blocked, so
  no `set_config` write-back or checkbox tick); the blank entry shows only when
  `get_current_config` matches no preset. Before that, every preset dropdown sat
  blank after each rebuild.
- **The button row is a sibling of the row grid, not inside it.**
  `configGroupBox`'s layout is `configOuterLayout` (a `QVBoxLayout` holding
  `configLayout`, the `QGridLayout` of rows, plus a separate `QHBoxLayout`
  button row) instead of the button being `addWidget`'d directly into
  `configLayout` with a `colSpan=number_columns`. A widget spanning that many
  grid columns forces Qt to allocate all of them even though only column 0
  had real content (2 groups, `number_config_columns` defaulting to 5) —
  squeezing the row grid's real column into a fraction of the group box's
  width, which is what made group-name labels render clipped/invisible.
  Tests: `tests/test_mmconfig_panel.py`.
- **The section's width is capped** (`_capConfigWidth`, re-applied by
  `rebuildConfigLayout`): `CONFIG_BLOCK_MAX_WIDTH_EM` x theme `font_px` per block of
  `number_columns` rows. A slider row's number field is capped (`_limitFieldWidth`)
  and the slider has stretch 1. Qt caps a whole grid **column** at its narrowest
  item's maximum, and if every stretched column is capped it hands the spare width
  to an unstretched one (pushing the capped section right), so `ResponsiveGrid.apply`
  also stretches the trailing column whenever all stretched columns are capped.
  Tests: `test_controls_panel_layout.py`, `test_ui_responsive_grid.py`.

`Core/MDAGlados.py` is the multi-dimensional acquisition layer that talks to MIL.

### Acquisition storage and scratch directories

Two backends, two data shapes. The pycromanager backends append an NDTiff `Dataset`
to `shared_data.mdaDatasets`; `MMCORE_PLUS` has no NDTiff store and instead writes a
`zarr.Array` into `shared_data.mdaZarrData`, **keyed by napari layer name** (`'MDA'`
is only `startMDAVisualisation`'s default — a Nodz-driven acquisition names the layer
after its node). `MDAGlados._resolve_finished_acquisition_data()` is the one place
that resolves the two; `_acquisition_storage_path()` is the one place that turns
either into a filesystem path. Note `zarr.Array.path` is the array's path *inside*
its store (`''` for a root array), not a location — the real directory is
`array.store.root`; and `zarr.open()` rejects an already-open `Array` outright
(zarr 3.x `TypeError: Unsupported type for store_like`). Both traps were live bugs
(T-D6). Tests: `tests/test_mda_acquisition_data.py`.

The multiDstack display zarr has exactly one creation site,
`napariGlados._create_mda_zarr(shared_data, layer_name, shape, h, w, dtype)` — called
by both `_preinit_mda_zarr` (pre-acquisition, dtype from `_camera_dtype()`:
`getBytesPerPixel() <= 1` → uint8 else uint16) and the display-path fallback in
`_napariUpdateLive_locked` (dtype from the frame in hand, so no `core.*` call on the
GUI thread). `dtype` is deliberately **required**, not defaulted: `zarr.open()` with
no `dtype=` yields a **float64** array on zarr 3.1.0, which is how every uint16 frame
used to get upcast on write (T-D1). The helper also registers the array into
`mdaZarrData[layer_name]`, resets `allMDAslicesRendered`, and owns the
`new_zarr_temp_dir` call. Tests: `tests/test_mda_zarr_store_creation.py`.

Dimension steps are set with **one** batched call (T-E1):
`napariViewer.dims.set_current_step(list_of_axes, list_of_values)`. napari's
`set_current_step` accepts sequences and that form routes through a single
`set_point`, which assigns `Dims.point` once; the scalar form assigns it per call and
each assignment emits a `point` event forcing a complete re-slice (chunk fetch,
decompress, contrast rescan, GPU upload). Measured on the pinned napari 0.7.0: 4 point
events for a 4-D per-axis loop, 1 for the batched call, identical resulting
`current_step`. Tests: `tests/test_dims_batched_update.py` (which also pins the
per-axis behaviour, so a future napari that stops coalescing fails loudly).

Auto-contrast defers to napari's own native "once"/"continuous" toggle (T-E2, revised):
new live/MDA/album layers seed `_keep_auto_contrast = True` at creation — the same flag
napari's built-in `AutoScaleButtons` (`qt_contrast_limits.py`, the "auto-contrast"
control in napari's own layer controls) reads for its initial checked state and writes
when the user clicks "continuous" or drags the contrast sliders manually (which the
user's own napari controls already leave at `False` after a manual set). Glados no
longer overrides the user's choice with a forced throttle: `_maybe_refresh_contrast`
checks `layer._keep_auto_contrast` first and does nothing at all when `False` ("once"
already consumed, or a manual/slider-set range the user wants held constant). While
`True` it still recomputes on a throttle
(`visualisation_config.contrast_refresh_every_n_frames`, default 10) rather than every
frame, but *only* for the **frameByFrame** path, whose in-place `layer.data[:] = ...`
update bypasses napari's own slicing pipeline entirely — nothing else would ever
refresh it. **multiDstack no longer calls this function at all**: its
`dims.set_current_step` already runs napari's normal slicing pipeline
(`_update_slice_response` in `napari/layers/image/image.py`), which natively recomputes
contrast on every re-slice while `_keep_auto_contrast` is `True`, and does nothing while
it's `False` — a second, redundant Glados-side throttle would just repeat the same scan.
Tests: `tests/test_contrast_throttle.py`.

The multiDstack layer's shape is validated **once per acquisition, not per frame**
(T-E3). An existing layer's shape cannot drift on its own, so
`_layer_shape_already_validated` caches the verdict on the only two things that can
invalidate it: `_mdaModeParamsGeneration` (the plan changed) and a **weakref** to the
layer (the layer object was replaced). The weakref is not decoration — `id(layer)` is
recycled by CPython for a freed object, which would report a brand-new layer as
already validated; that is the T-D5 bug. A failed check pops the layer, nulls the
store and releases its temp directory, discarding every frame written so far, so it
now logs at INFO: after T-E3 it must happen at most once per acquisition, and a second
occurrence in one run is a real signal. Newly created layers are marked validated at
creation (they are built from the same dimensions). Tests:
`tests/test_layer_shape_validation_cache.py`. **That per-dim check only ever
walked the leading (acquisition) dims, never the trailing image plane** — two
acquisitions reusing the same layer name (e.g. the default `"MDA"`) with the
same leading dim counts but a different camera frame size (a ROI/binning
change between them) passed the check regardless, so the stale store's `(h,
w)` silently stayed whatever the *previous* acquisition's frame size was, and
the first write of the new acquisition failed with a zarr "could not
broadcast" error. Fixed by also comparing `layerData.shape[-2:]` against the
incoming frame's shape once the per-dim loop completes clean (a `for/else`).
`_preinit_mda_zarr` (the MMCORE_PLUS fast-camera pre-creation path, above) had
the same root bug in a different shape: it only ever checked
`mdaZarrData.get(layerName) is not None` and, if so, reused whatever was there
unconditionally — so a store left over from a *differently-shaped* previous
acquisition under the same layer name (different leading dim count, e.g. a
prior z-stack reused for a t-only run, or a different frame size) was written
into as though it still matched, and every `ZarrFrameWriter` write of the new
acquisition raised "too many indices"/"could not broadcast" and the whole
acquisition's data was lost. It now compares the full expected shape
(`tuple(n_entries_in_dims) + (h, w)`) and dtype against the existing array,
reusing it only on an exact match and otherwise discarding it (`mdaZarrData[layerName]
= None`, `release_zarr_temp_dir`, `_invalidate_layer_shape_validation`) before
creating a fresh one — the layer-shape-validation cache invalidation is what
then makes the display path above rebuild the napari layer too, on the first
frame of the new acquisition. Tests: `tests/test_preinit_mda_zarr_reset.py`.
Both reuse sites (`_preinit_mda_zarr` and the display path's layer-creation branch) now
go through `_discard_mismatched_mda_zarr(shared_data, layer, expected_shape, dtype)`. The
display branch used to reuse *any* existing store: after the user closed the `MDA`
layer (nothing releases its store then) and changed the plan, every frame of the next
pycromanager-backend MDA failed with zarr `BoundsCheckError` and nothing was shown.
Two first-frame GUI-thread costs were moved off it (measured on a 10 ms, 500 t x 3 z
Python-backend MDA on inSiliScope: first display update 6.9 s -> 2.1 s, the rest is
napari's own `add_image`): `import zarr` (~4 s under GIL contention; now
`prewarm_display_imports()` on a daemon thread at startup-ready) and store deletion
(`Shared_data._discard_temp_dir` renames the directory, then `rmtree`s it on a daemon
thread; 1500 one-frame chunk files took 3.3 s; `release_all_temp_dirs` stays
synchronous because `os._exit` follows). Tests: `tests/test_fast_mda_display_start.py`.
**The multiDstack layer is now built at the Acquire click, not on the first frame**
(first display update 2.1 s -> ~0.05 s on the same MDA). `startMDAVisualisation` ends with
`_precreate_mda_layer`: a short-lived thread reads the camera size and `_camera_dtype`,
then posts `_build_mda_layer` to the GUI thread via the napari bridge, skipped if `mdaMode`
went off or `_mdaModeParamsGeneration` changed meanwhile. Not on `MMCORE_PLUS` (its
`_preinit_mda_zarr` owns the store). The first frame goes through
`_prepare_mda_layer_for_frame`: a layer whose shape/dtype matches the plan is just marked
validated (the pre-build leaves it unvalidated on purpose, since binning is not in the ROI);
otherwise it builds with the frame as the seed and stamps `ZARR_WRITTEN_SLICE_KEY`.
`_build_mda_layer` **re-points** a same-ndim existing layer (`layer.data = store`) instead
of delete + `add_image` (napari's controls, sliders and GL texture are the ~2 s); a
different ndim still replaces the layer (see the Album note: ndim is fixed at creation).
`warm_up_napari_image_layer` adds and removes a hidden tiny layer at startup-ready to pay
napari's first-image-layer cost early. Tests: `tests/test_mda_layer_build.py`.
**The end-of-MDA backfill fills around the cursor.** `_backfill_missing_slices(...,
cursor=, on_current_slice_filled=)` re-sorts the remaining slices by L1 distance to
`viewer.dims.current_step` (only when the cursor moved), and `_finalise_mda_layer`
connects `dims.events.current_step` for the duration and repaints when the slice under
the cursor lands (0.23 s after a scrub in the repro, vs. waiting for the whole pass).
Tests: `tests/test_mda_backfill.py`.
**Layer-list thumbnails no longer spin forever** (`GUI/napari_layer_list.py`,
`install_layer_list_patches()` from `InitateNapariUI` and the plugin `MainWidget`). napari
0.7 marks a layer unloaded per async slice request and paints the spinner *instead of*
the thumbnail; every displayed MDA frame moves the dims, so the newest request was always
pending. The patched `LayerDelegate` always paints the thumbnail and overlays the spinner
only once a layer has been unloaded *and* its thumbnail unchanged for `SPINNER_DELAY_S`
(1 s); unloaded time alone left a permanent spinner over a working MDA thumbnail (the
layer stays unloaded all acquisition). Thumbnail progress = identity of `layer.thumbnail`
(its setter assigns a new array). It patches private napari
methods; `tests/test_napari_layer_list.py` pins them so an upgrade fails loudly.

**Fixing that reset exposed a second, narrower race in `add_image()` itself**:
once `_preinit_mda_zarr` reliably produces a correctly-shaped store, frames
actually reach the disk-write queue, and the very first `add_image()` call for
a freshly-attached multiDstack layer can now land *while the ZarrFrameWriter
thread is still mid-write of the exact chunk napari reads first*. zarr's
`LocalStore._put` is not atomic — it opens the chunk file with mode `"wb"`,
which **truncates it to 0 bytes on open**, then writes the bytes — so a read
landing in that window gets a 0-byte chunk and crashes napari's own async
`_LayerSlicer` thread pool with `ValueError: cannot reshape array of size 0
into shape (...)`, entirely outside anything Glados can catch (it is not on a
Glados thread). Every *explicit* read this codebase drives is already race-free
via `_slice_safe_to_display` (it only ever points `dims.point` at a
writer-confirmed slice) — `add_image()` is the one napari-internal read
nothing previously controlled the target of, since it reads whatever
`dims.point` already is (all-zeros for a brand new layer) practically
immediately once the layer is attached. The non-preinit branch (array created
here, not by `_preinit_mda_zarr`) was always safe because it seeds slice `(0,
0, ...)` with the current frame *synchronously*, before `add_image()`; the
preinit branch skipped that seed (to avoid losing the frameReady writes
already queued) with nothing else guaranteeing the write had landed.
`_wait_for_zarr_writer_progress(shared_data)` closes the gap: it blocks
(bounded, `ZARR_WRITER_FIRST_WRITE_TIMEOUT_S` = 5 s, best-effort — logs and
proceeds rather than hanging forever) until `writer.last_written_tag` is no
longer `None`. Waiting for *any* completed write rather than specifically
`(0, 0, ...)` is sufficient and simpler: the frame-ring consumer submits to
the writer's single queue in arrival order and multiDstack uses the deep ring
(every frame reaches storage), so whatever the writer completes first is
necessarily the first frame submitted. Tests:
`tests/test_wait_for_zarr_writer_progress.py`.

Album mode (`napariHelperFunctions.addToExistingOrNewLayer`, one caller —
`MMcontrols.addImageToAlbum`) appends into a **geometrically grown buffer** kept in
`layer.metadata` (`ALBUM_BUFFER_KEY` / `ALBUM_COUNT_KEY`, start 4 frames, double when
full), and hands napari `buffer[:count]` — a view, so O(1) per snap (T-E4). It used to
`np.append` the whole stack *and* destroy and rebuild the layer with `add_image`,
hand-copying twelve display properties across, per snap: measured over 50 snaps of a
512x512 uint16 frame, 1.6 -> 14.5 -> 41.2 ms for the 2nd/20th/50th against a flat
~0.13 ms. The `data` is **assigned**, not mutated in place as the frameByFrame path
does, because the stack gets one frame longer each time and only an assignment tells
napari its extent grew. The buffer takes its dtype from the incoming frame — the old
bare `np.zeros((2, h, w))` was float64, so a uint16 album cost 4x the bytes from its
second snap on. A frame-shape change mid-album (ROI/binning) starts a fresh stack and
logs at INFO, where `np.append` raised. The layer is created **3-D from the first snap**
(`buffer[:1]`, scale `[1, px, px]`): napari 0.7.0's vispy layer sizes
`_world_to_layer_units_scale` to the layer's ndim once, at creation, so a layer whose ndim
grows later raises `IndexError: tuple index out of range` in `_on_matrix_change`. **Never
change a napari layer's ndim after creation**; replace the layer instead.
Tests: `tests/test_album_layer_growth.py`.

That store is created **uncompressed, one frame per chunk, via
`zarr.create_array`** (T-D3). `zarr.open` cannot set compression at all on zarr 3.1.0
— it rejects `compressor` ("cannot be used for arrays with zarr_format 3") *and*
`compressors` (unexpected keyword) — so the helper uses `create_array`. Both choices
are measured, not assumed (1024x1024 uint16 frames): dropping Zstd on a scratch store
that gets deleted anyway writes at ~9.1 ms/frame against ~12.8 ms and serves a slice
back to napari in ~2.8 ms against ~7.9 ms, for ~17% more bytes. Multi-frame chunks
were **rejected**: napari paints a multiDstack layer by reading one slice out of this
same array, so chunk size is on the display path, and even with perfectly batched
whole-chunk writes 8-/32-frame chunks were slower to write *and* 5-17x slower to read.
The cost of that decision is one file per frame (see `docs/plans/claude_issues_and_features.md`).

The zarr write itself runs on a **dedicated writer thread**,
`GUI/frame_writer.py`'s `ZarrFrameWriter` (T-D3). `_try_write_frame_to_zarr` computes
the slice index and calls `writer.submit(destination, image)`; the writer's thread does
the disk work. It differs from `FrameRing` on both axes deliberately: its queue is
bounded **by bytes** (`DEFAULT_MEMORY_BUDGET_BYTES`, 256 MB, so the depth adapts to
frame size) and it applies **backpressure** rather than overwriting the oldest — a
stale display frame is worthless, but a dropped storage frame is lost data, and on
`MMCORE_PLUS` there is no NDTiff store to recover it from. `submit` blocks with a
timeout (`DEFAULT_SUBMIT_TIMEOUT_S`, 5 s) so a wedged disk cannot make an acquisition
uncancellable; on timeout the frame is counted and logged loudly. The writer is
started lazily on the first frame (keyed on the array object, so a re-created store
retires the old writer) and drained by `_stop_zarr_writer()`, which
`_stop_frame_ring_consumer` calls **after** joining the ring consumer — that ordering
matters, since the consumer is what submits, and the finalisation pass must not read
the store with writes still in flight. Simulated against the real ring at 30/60/120
fps with 2.1 MB frames, this takes the consumer thread (which also feeds display and
every RT-analysis queue) from ~33-41 ms blocked per frame to ~0.05 ms, with no frames
lost. It absorbs *bursts*, not a sustained overrun — `max_depth` and
`blocked_seconds` in the teardown log are what distinguish the two. Tests:
`tests/test_frame_writer.py`, `tests/test_zarr_single_writer.py`. Because the write
is queued, the display must **not** be pointed at the frame that just arrived —
`_slice_safe_to_display()` follows `writer.last_written_tag` (published only after the
write returns) so napari renders the newest slice that genuinely exists. Skipping this
is what made a multiDstack MDA show a black live view during acquisition and a perfect
stack afterwards: an unwritten slice of a fresh store is zeros.

That every-frame writer is **`MMCORE_PLUS`-only**. Both pycromanager acquisition
callbacks (`grab_image_liveVisualisation_and_liveAnalysis` and its `_savedFn`
sibling) do no acquisition-side zarr write at all, so there the fps-throttled
display path is the store's only writer and most slices are missing when the
acquisition ends. `_backfill_missing_slices` (T-D4) fills them from the NDTiff
`Dataset` at finalisation. It is gated on `shared_data._mdaModeAcqData._dataset`,
which is assigned only inside the pycromanager `Acquisition` context managers —
so the pass is skipped outright on `MMCORE_PLUS`, where it never had a dataset to
read and never filled anything. `shared_data.allMDAslicesRendered` is a **`set`**
of `_axes_key` tuples (sorted `(key, value)` pairs), not the old
running-integer-keyed dict: the membership test is per-expected-event, and the
dict form made it O(N_events x M_rendered) dict-subset comparisons *plus* a
`time.sleep(0.001)` per missing frame, on the GUI thread — a multi-second freeze
at the end of a large MDA. Subset semantics are kept (a frame's `metadata['Axes']`
can carry keys the event's `axes` does not) by projecting the rendered set onto
the expected event's key names once per distinct key set. Tests:
`tests/test_mda_backfill.py`.

Each frame reaches that store **once** (T-D2). The acquisition-side writer
(`_try_write_frame_to_zarr`, on the frame-ring consumer thread) stamps the frame's
metadata dict with `napariGlados.ZARR_WRITTEN_SLICE_KEY` = the slice tuple it wrote,
and the display path in `_napariUpdateLive_locked` skips its own write (and the
identical `searchsorted` recompute) whenever that stamp is present, reusing the index
to step the napari dims. The stamp is a per-frame fact, not a per-backend guess: both
pycromanager paths (`image_process_fn` / `image_saved_fn`) do no acquisition-side zarr
write at all, and a ring write that raises stamps nothing, so in either case the
display path stays the writer. It survives the GUI's second `metadata_refactor` call
only because that function mutates its argument in place and returns it. Tests:
`tests/test_zarr_single_writer.py`.

Every scratch store lives in a `tempfile.TemporaryDirectory` whose *object* is the
store's lifetime — its finalizer `rmtree`s the directory. `Shared_data` owns them
all: `new_zarr_temp_dir(layer_name)` / `release_zarr_temp_dir(layer_name)` over the
per-layer `mdaZarrTempDirs` dict, `new_pyMMC_temp_dir()` for the NDTiff scratch
dataset, and `release_all_temp_dirs()` wired to `aboutToQuit` — needed because the
app force-exits through `os._exit(0)` and runs no finalizers. Never construct a
`TemporaryDirectory` inline and keep only `.name` (T-D7). Tests:
`tests/test_temp_store_lifetimes.py`. **`MMCORE_PLUS` saves via pymmcore-plus itself.** That backend has no NDTiff
engine, so `run_mda(output=<path>)` does the recording: `napariGlados.mmcore_output_path()`
builds `<Storage folder>/<name>.ome.zarr` (or `.ome.tiff`) from the
`MDAConfig.mmcore_save_format` dropdown — `'none'` acquires without saving — suffixing
`_1`, `_2` … rather than overwriting an existing acquisition, since pymmcore-plus
dispatches its writer off the file extension (`handler_for_path`). The runner thread is
joined after `mda.is_running()` goes False, because an OME-TIFF handler assembles the
stack on `sequenceFinished` and the storage path is reported to nodz immediately after.
`shared_data.mdaSavedPath` records where it landed and `_acquisition_storage_path()`
prefers it over the scratch store's temp directory. Before this the branch ignored the
Storage folder completely and an MDA on this backend saved **nothing**. The scratch zarr
remains, as what it always was — the display buffer, not the archive. Tests:
`tests/test_mmcore_mda_saving.py`, which drives pymmcore-plus' bundled demo camera, so
the saving claim is verified rather than reasoned about — that demo camera makes
`MMCORE_PLUS` acquisition testable headlessly in general.
**`ndtiff` is that backend's default save format, written by Glados (T-D8).**
pymmcore-plus has no NDTiff sink, so the MDA worker opens an `NDTiffDataset` at a
pycromanager-style `<name>_1` directory (`mmcore_output_path`) *before* `run_mda`,
which then gets `output=None`; `grab_image_liveVis_PyMMCore` queues each frame to an
`NDTiffFrameWriter` (`submit_ndtiff_frame`, `event.index` mapped to pycromanager's
`time`/`channel`-name/`z`/`position` axes, a *shallow copy* of the metadata because the
ring consumer mutates the original) *before* the ring push, so an archived frame has
backpressure instead of being shed by the overwrite-oldest ring. `_finish_ndtiff_store()`
drains the writer, `finish()`es the dataset and `appendNewMDAdataset`s it -- after
`_stop_frame_ring_consumer()` and again, idempotently, in the worker's `finally`.
`frame_writer.py` is now `FrameWriter` (queue/backpressure/stats) with `ZarrFrameWriter`
and `NDTiffFrameWriter` subclasses. `shared_data.mdaCurrentDataset` (reset at each MDA's
start, set by `appendNewMDAdataset`) is what `_resolve_finished_acquisition_data` prefers,
because `mdaDatasets[-1]` can now be an earlier acquisition's. The dead scratch
`NDTiffDataset` `PyMMCore_startedAcqCallback` used to create is gone. Why NDTiff is the
default -- and why the plan's numbers no longer applied: pymmcore-plus 0.18's
`run_mda(output=...)` goes through **ome-writers** (tensorstore for `.ome.zarr`), whose
default buffers the whole acquisition in RAM until close -- see `docs/plans/claude_decisions.md`
(T-D8) and `make bench-storage`. Tests: `tests/test_mmcore_ndtiff_saving.py`,
`tests/test_ndtiff_frame_writer.py`.

`MDAConfig.live_mode_method` (`sequence` | `mda`, default `sequence`) selects between
the continuous-sequence live path and the legacy 999-frame-MDA loop;
`MDAConfig.live_pull_policy` (`latest` | `sequential`, default `latest`) selects which
frame that path takes from the circular buffer and applies only to `sequence`.
`live_mode_nr_frames` applies only to `mda`. Both new settings appear as dropdowns in
Advanced Settings; a config saved before they existed simply keeps the defaults
(`load_config_from_json` only overwrites keys present in the JSON).

### Shared state — `GUI/sharedFunctions.py`

`Shared_data` is the single object passed everywhere (UI, worker threads, napari plugins, autonomous microscopy nodes). **`shared_data.core` is only assigned on the napari-plugin path**; on the standalone app it was an empty-list placeholder, so its getter now falls back to `MILcore` while nothing real is assigned (a full recipe run crashed on that `[]`). New code should use `shared_data.MILcore` directly. It holds `core`, the MIL instance, config dataclasses, analysis-thread lists (`LoggingList` is a list subclass that emits Qt signals on mutation), and live/acquisition state flags. When adding cross-component state, add it as a field on `Shared_data` rather than a global.
The Slack client is `webhook_config.slack_client`, built by `notify/slack.py`'s
`make_slack_client(token)` (a `slack_sdk.WebClient`, or None without a token); the old
`slack==0.0.2` dependency was an unrelated package.

`_mdaModeParams` is a property: MDA mode assigns an already-converted pycromanager
event list, live mode assigns a raw `useq.MDASequence` that the getter converts (and
caches) only if something actually reads it. Its setter bumps
`_mdaModeParamsGeneration`, the key for caches derived from the event list —
`napariGlados._get_cached_dimensions` today. Bump that counter from any new
assignment path, and key new event-list-derived caches on it rather than on
`id(params)`: an address is not an identity (CPython recycles freed ones), which is
the T-D5 bug. The getter's lazy conversion deliberately does *not* bump it — same
acquisition, just materialised.

### UI — `GUI/`

- `GUI_napari.py` — standalone entry. Builds a `headlessGUI` for backend choice, spawns Napari, runs `runNapariPycroManager` in a `Worker`/`QThread`. Sets `NAPARI_ASYNC=1` and `NAPARI_OCTREE=1` *before* importing napari. The MM-path and config-file fields each have a down-arrow `QToolButton` listing the last 20 values used (`MicroManagerConfig.path_history` / `config_path_history`, most recent first, recorded on Start via `headless_validation.push_path_history`). List-typed config fields need `setting(..., default_factory=list)`. Tests: `tests/test_headless_path_history.py`.
- `_dock_widget.py` — napari plugin entry. `MainWidget` constructs `Shared_data`, calls `pycromanager.Core()` directly, and adds three dock widgets — all of which inherit `GladosWidget` (Performance Mode is a separate `napari.yaml` command):
  - `MMConfigWidget` — Micro-Manager config groups, stages, ROI (`microManagerControlsUI_plugin`)
  - `MDAWidget` — Multi-D acquisition (`MDAGlados_plugin`)
  - `AutonomousMicroscopyWidget` — recipe graph (`autonomousMicroscopy_plugin`)
  Pattern: the parent `MainWidget` creates `core`, `shared_data`, `MM_JSON`, `livestate`, and child widgets read them off `parent.*` in their `__init__`.
- `GUI/napariGlados.py` — `napariHandler` and the real-time visualisation/analysis loop (`napariUpdateLive`, etc.). Uses `napari.qt.thread_worker` and yield-based generators, which is why several update functions live at module scope rather than inside a class.
  - **Live mode (T-C3):** `MDAConfig.live_mode_method` selects the path.
    `sequence` (default) runs `napariHandler.run_liveSequence_worker` — a plain
    continuous sequence acquisition (`MIL.start_continuous_sequence_acquisition`) whose
    loop reads the circular buffer and pushes straight into the T-A7 frame ring. No
    acquisition engine, no `MDAEvent`, no per-frame pydantic validation; an A/B profile
    under `--auto-demo --profile-runtime` shows `_iter_exec_output` /
    `exec_sequenced_event` disappearing from the top-25 entirely. It is backend-blind
    (only T-C1 MIL primitives), blocks until `self.acqstate` goes False, and synthesises
    the metadata dict itself (`Axes = {'time': n}` plus `Time`/`Exposure`/`PixelSize_um`/
    `ROI`, the latter three read once per acquisition, not per frame) because there is no
    `mda_event` for `utils.metadata_refactor` to derive `Axes` from. `live_pull_policy`
    picks `get_last_image_and_metadata()` + `clear_circular_buffer()` (`latest`, cannot
    overflow) or `pop_next_image_and_metadata()` (`sequential`, every frame in order);
    anything that is not literally `'sequential'` is treated as `latest`. `mda` keeps the
    legacy 999-frame-MDA-in-a-loop path completely untouched as an escape hatch.
    A configured `vis_method='multiDstack'` is overridden to `frameByFrame` for the
    duration of sequence live mode (T-C4): that rendering indexes a zarr store by
    acquisition axes and the sequence path has none, so live frames would otherwise be
    aimed at whatever store `shared_data.newestLayerName` last pointed at. The override
    is a handler flag (`_live_sequence_active`) read via `_effective_vis_method()`, never
    a write-back to the user's config; it is lifted in the worker's `finally`, after the
    ring consumer has drained. MDA-mode `multiDstack` is unaffected. The display side
    needed no change — `_napariUpdateLive_locked` already routes any `'Live'`-named frame
    to its `frameByFrame` branch regardless of `vis_method`.
    Tests: `tests/test_live_sequence_worker.py`.
    **The pull loop is paced (`LivePollPacer`, module scope in `napariGlados.py`).** A flat
    0.5 ms idle polled ~21x per frame at 50 ms exposure, each poll a `_hardware_locked` MIL
    call holding the GIL. After a frame the pacer idles `COARSE_FRACTION` (0.9) of the
    frame interval in one go, then polls every `FINE_FRACTION` (3 %) of it, clamped to
    `[MIN_IDLE_S, MAX_IDLE_S]` = [0.5 ms, 50 ms]. The interval is an EMA of per-frame gaps
    seeded from the exposure; `_live_sequence_pull_once` returns the **number of camera
    frames consumed** (the `latest` policy can skip several), and `frame_arrived(frames=n)`
    divides the gap by it — counting a skip as one long interval fed back into ever-longer
    sleeps. One sample is also clamped to 2x the estimate so a stall cannot inflate it.
    `MicroscopeService.start_streaming(idle_sleep=)` accepts a callable, and the idle wait
    blocks on the **request queue** (`_stream_idle_wait`), so a stage move ends a long
    pacing sleep immediately. Tests: `tests/test_live_poll_pacer.py`.
  - **2-D display layers are `FastImage`s (`GUI/fast_image_layer.py`).** A napari `Image`
    subclass created via `add_fast_image(viewer, data, **kw)` — the Live/frameByFrame layer,
    every RT-node `'image'` layer (`layer_group.create_layer`, so AppData plugin nodes too)
    and `napariOverlay`'s legacy image overlay. For a same-shape/dtype 2-D numpy update on
    the GUI thread with a 2-D display, both `layer.data = x` and `data[:] = x; refresh()`
    skip napari's async path (`events.data` → viewer reassigns `dims.range` → async slice →
    `_on_slice_ready` → thumbnail + highlight): they do napari's *own* sync branch
    (`set_view_slice()` + `_refresh_sync`) with the thumbnail throttled to
    `THUMBNAIL_INTERVAL_S` and continuous auto-contrast to every `contrast_every_n_frames`.
    Measured 23 ms → ~3-5 ms per frame at 256², 27 → ~4 ms at 2048². Semantics stay napari's:
    `layer.data is x` holds, the view is re-sliced from `x`. Anything else (shape/dtype/ndim
    change, zarr/dask, multiscale, RGB, 3-D display, hidden, off-thread) falls through to
    stock `Image`. Three gotchas: napari's slice handler rescans contrast on **every** sync
    slice while `_keep_auto_contrast` is set, so `_fast_update` holds that flag off around
    `set_view_slice()`; napari's layer metaclass runs a post-init `refresh()` after
    `__init__` returns (counters start at 1); a stub viewer without `add_layer` gets a stock
    `add_image` layer. `events.data` is skipped on purpose — its listeners only recompute
    dims ranges/ndim, which cannot change here. Tests: `tests/test_fast_image_layer.py`.
  - **Every hand-off to the GUI thread is one deep (display backpressure).** The display
    worker's `yield` and each RT node's `_do_visualise` emit are both *queued* Qt
    connections, and neither used to check whether the GUI thread had drawn the previous
    payload — so payloads accumulated in Qt's event queue and the display drifted
    unboundedly behind the camera. Note `_should_display_now` does **not** prevent this and
    actively makes it worse: it decides on `now - shared_data.last_display_update_time`,
    stamped only at the *end* of a completed GUI update, so it measures starvation rather
    than backlog and opens wider the further behind the GUI falls. It is the *rate* limit;
    the *depth* limit is `shared_data.displayUpdateInFlight` via
    `napariGlados._claim_display_slot()` / `_release_display_slot()`, and
    `AnalysisThread_customFunction_Visualisation._claim_visualise_slot()` for the overlay
    path. **A producer refused a slot must drop its frame, never hold it** — holding just
    relocates the backlog. Both slots are watchdogged (`DISPLAY_INFLIGHT_TIMEOUT_S` /
    `RT_VISUALISE_INFLIGHT_TIMEOUT_S`, 5 s) because a payload that never arrives would
    otherwise freeze that display for the session, and both are released *unconditionally* —
    `napariUpdateLive` wraps its whole body because it has four early returns, and missing
    any one of them wedges the display. Any **new** path that marshals frames to the GUI
    thread must claim and release a slot the same way. Tests:
    `tests/test_display_backpressure.py`.
  - **Live/MDA stop→start race guard:** the two `napariHandler`s (`shared_data._livemodeNapariHandler` / `_mdamodeNapariHandler`) are constructed once per session and reused for every toggle, so rapid Live/MDA on-off-on toggling could previously start a new `run_MILCoreAcquisition_worker` (QThreadPool job) while the old one was still tearing down the same `core.mda`/`Acquisition` object (`stop_sequence_acquisition()` is fire-and-forget) — two threads driving the same native MMCore/Java engine concurrently, causing native access violations under stress testing. `napariHandler` now has `_acq_transition_lock` (an `RLock`, since the worker's own cleanup re-enters `acqModeChanged` from its own thread) and `_worker_stopped_event`: `acqModeChanged`'s ON path waits (`ACQ_STOP_TIMEOUT_S`, default 10s) for the previous worker to fully exit before starting a new one, refusing to start (and reverting the mode flag) rather than racing if the timeout is hit.
  - **Frame ring (MMCORE_PLUS `frameReady` path):** `grab_image_liveVis_PyMMCore` is connected with `Qt.DirectConnection`, so it runs synchronously on pymmcore-plus' own MDA thread — everything it does happens in front of the next camera frame. It is therefore a pure hand-off: `frame_ring.push(image, metadata)` and return. `GUI/frame_ring.py`'s `FrameRing` is a bounded, overwrite-oldest, stdlib-only buffer (drop-counting, with an `Event` the consumer waits on); `napariHandler._frame_ring_consumer_loop` (a plain daemon `Thread`, started just before the `frameReady` connect and stopped just after the disconnect, plus an idempotent stop in the acquisition worker's outer `finally`) does the real per-frame work: `metadata_refactor`, the multiDstack zarr write, and `put_data_in_visualisation_and_analysis_queues`. Two capacities: `FRAME_RING_CAPACITY_DISPLAY` (4) for live, since display and RT analysis drop frames at their own gate anyway, and `FRAME_RING_CAPACITY_STORAGE` (256) for multiDstack MDA, where a dropped frame is a permanently black slice with no NDTiff store to backfill from. The per-acquisition drop tally is logged at teardown (WARNING if non-zero). The pycromanager `image_process_fn` / `image_saved_fn` paths do **not** use the ring — `image_process_fn` must return `(image, metadata)` synchronously for pycromanager to store the frame.
- **Startup window layout** (`napariGlados._finaliseStartupLayout` / `_sizeControlsDock`,
  queued by `QTimer` at the end of `runNapariPycroManager`): maximise, select the Controls
  tab, and `resizeDocks` the top area to the Controls content height (capped at
  `STARTUP_CONTROLS_MAX_HEIGHT_FRACTION` of the window). It must run from the event loop:
  a `raise_()` on a tabified dock before Qt builds the tab bar is ignored, and the last-added
  tab wins. The maximise first clears `WindowMaximized`, because napari restores a saved
  maximised flag with a stale size and `showMaximized()` is then a no-op.
  The top area is sized for the **taller of the Controls and Multi-D acquisition tabs**
  (`alsoFit`), each measured at the Controls width by `_dockContentHeight`
  (height-for-width, so a wrapped `FlowRow` line counts; the scroll area uses it too).
  `_correctControlsDockHeight` then re-measures and adds the deficit: Qt takes the
  tabified docks' tab bar (~25 px) out of the `resizeDocks` height, which used to clip
  the bottom row. The settings-save resume and the `'startup layout finalised'` mark
  live there now. Tests: `tests/test_startup_controls_dock_height.py`.
- **UI toolkit — `ui/layout/` (the MDA and Controls docks are built on it).** Rules:
  **never set a font, margin, padding or colour on an individual widget** — spacing
  comes from `current_theme()` when a layout is built, and looks come from the one
  stylesheet `build_stylesheet(theme)` (applied to the three standalone docks by
  `runNapariPycroManager`, and by `GladosWidget.__init__` on the plugin path), styled
  per widget by a `gladosRole` property set with `set_role()` (`section`, `primary`
  for Acquire, `readonly`, `warning`/`normal`). The pieces:
  - **The docks are dense:** `build_stylesheet` derives padding/margin as
    `compact_padding`/`compact_margin` (half the stored `widget_padding_px`/`widget_margin_px`;
    buttons a little taller), line edits get 1 px borders, and section-internal spacing is
    `compact_spacing`. Derived, not stored, because `glados_state.json` keeps the old
    Theme defaults verbatim -- changing a default would not reach existing installs.
  - `theme.Theme` — every size/colour; defaults reproduce the old inline
    `ScaledStylesheet` (14 px font and Windows metrics x0.75). Persisted as the
    all-hidden `LayoutConfig` (`config.layout_config`, same field names, fed through
    `theme_from_config`, read once at startup) — the storage for a future
    layout-settings UI. `hidden_sections` there (comma-separated section keys) is
    honoured by both panels.
  - `Section(title, key, layout)` — a titled `QGroupBox`; `key` (`"mda.z"`,
    `"controls.stages"`) is how a grid places it. `set_active()` is `setEnabled`, so
    `get_MDA_events_from_GUI`'s `isEnabled()` gating is unchanged. The theme's QSS
    zeroes group-box padding, so `Section` reserves room for its title itself.
  - `FormGrid` (label | field | trailing, field stretches; a lone field spans the
    trailing column), `FlowRow` (wraps when narrow), `ListEditor` (table + top-aligned
    button block, `button_columns` wide (default 2), filled row by row;
    `configure_table_header` sizes columns from header text and widest cell and sets a
    `table_min_rows` minimum height, overridable per editor with `min_rows` — never a
    fixed height/width). The MDA lists use `MDA_LIST_MIN_ROWS` (3), so that tab fits
    the startup dock height. The table's minimum width is recomputed when rows change.
    It counts the row header via `isHidden()`, not `isVisible()`: the table is unshown
    at construction, and leaving the row header out clipped "Channel Setting".
  - `ResponsiveGrid` — `register(key, widget)` once, `set_placements({bucket:
    [Placement(...)]}, column_stretch={bucket: {key: n}})`, then `apply(bucket)` only
    **moves** widgets (no-op when unchanged). Buckets come from `classify_shape(w, h)`,
    the single classifier both hosts use. Hidden/unbuilt sections close ranks: only
    single-cell placements claim a row/column, so a spanning bar shrinks with them.
    `bucketChanged` lets a section rearrange its insides (the MDA storage bar stacks
    into two rows when tall, `_arrangeStorageBar`).
  - Panels keep `self.gui` / `self.mainLayout` as the `QGridLayout` hosts embed
    (`addLayout`, `setLayout`, the Nodz MDA/MM-config dialogs); it holds just the
    `sectionGrid`. Placements live at module scope: `MDA_SECTION_PLACEMENTS` in
    `MDAGlados.py`, `CONTROLS_SECTION_PLACEMENTS` in `MMcontrols.py`. Both panels have
    `handleSizeChange(size)`, wired to the standalone dock's `sizeChanged`;
    `GUI_grid_width` now holds the bucket (a legacy int column count still maps).
  - To add a section: build a `Section`, `register` it, add a `Placement` per bucket.
  - Offscreen screenshots need `QT_QPA_FONTDIR=C:/Windows/Fonts`, or Qt renders no text.
    Import `PyQt5.QtWebEngineWidgets` before creating the `QApplication` when the script
    imports `GUI.utils`; `show()` on a `QMessageBox` under `offscreen` segfaults (grab
    without showing). A test-made `QApplication` must stay referenced, or it is collected
    and `QApplication.instance()` is `None` again.
  - Stages section (`MMConfigUI.stagesLayout`): two independent blocks, each hidden when
    its stage is missing. XY is `ui/widgets/stage_dial.StageDial` (3 rings x 4 directions,
    inner = smallest step; emits `stepRequested(dx, dy, size)`, `_onXYDialStep` moves by
    `XYMoveEditField[X_/Y_<size>]`; it doubles as `XYStageInfoWidget`, a `setText`
    readout) over a step table whose FOV buttons sit under the column they fill. Z is
    dropdown / rail / step fields; step columns are sized by `_stepColumnWidth`. The dial colours blend the palette's Window/WindowText only --
    under napari's dark QSS, Button/Base keep Qt's light defaults. Advanced settings
    support `input_type="checkbox"` (stores a real bool; `utils.settingIsTrue` reads either
    form) -- used by `VisualisationConfig.show_scripts_section` (Scripts box, default off).
    `LayoutConfig` must stay all-hidden (`test_ui_theme` pins it).
  Tests: `tests/test_ui_theme.py`, `tests/test_ui_responsive_grid.py`,
  `tests/test_ui_list_editor.py`, `tests/test_mda_gui_rebuild.py`, `tests/test_stage_dial.py`,
  `tests/test_controls_panel_layout.py`. Widget-identity tests compare
  `sip.unwrapinstance()` addresses, never `id()` of a PyQt wrapper (not stable).
- `GUI/nodz/` — vendored Nodz graph editor, used to render and edit autonomous-microscopy recipes (JSON, e.g. `AutonomousMicroscopy/ExampleRecipes/01_simple_timelapse.json`). Recipes have three regions: Initialisation (pink), Scoring (green), Acquisition (yellow).

### Autonomous microscopy — `AutonomousMicroscopy/`

- `MainScripts/FunctionHandling.py` — `argumentChecking`, the kwarg check nodes call. The executor itself is `autonomous/executor.py`; dispatch is `autonomous/registry.py`.
- `Analysis_Measurements/` — measurement nodes (StarDist, AverageImage, etc.).
- `Real_Time_Analysis/` — RT analysis nodes (FFT, pSMLM, sharpness, BioImage Model Zoo, frame counters).
- `CustomFunctions/` — site-defined helpers (autofocus, stroboscopic lasers).

**Plugin discovery (important):** the `__init__.py` in each of these three folders imports every `.py` in it through `plugins/discovery.py`'s `load_node_modules` (failures are logged, not swallowed). The matching AppData folder, `appdirs.user_data_dir()/Glados-PycroManager/AutonomousMicroscopy/<subfolder>/` (`user_appdata_dir_for`), is scanned too (see the reload note below for when).

So **users add new analysis/RT/custom nodes by dropping a `.py` into the AppData folder, not into the source tree.** When searching for a node implementation, check both locations. A node needs a module-level `__function_metadata__()` *and* `@register("<stem>.<function>")` on each callable (`autonomous/registry.py`); without the decorator the node shows in the GUI but the recipe cannot dispatch it. The user-facing guide is `docs/developer/writing-nodes.md`.

**Plugins > Reload Glados Custom Nodes** (`discovery.reload_all_node_modules`). The
package `_load_appdata()` is never called at startup: AppData nodes are first imported
by `utils.functionNamesFromDir` under their **bare stem** (`sys.modules["MyNode"]`), and
`_resolve_node_obj` checks the bare stem first. So the reload also purges every
`sys.modules` entry loaded from a node folder (`_purge_modules_in`); without that an
edited AppData node kept its old kwargs. UI built from node metadata once must
rebuild on reload: register with `discovery.add_reload_listener` (held weakly).
`RTAnalysisPanel` does (`reloadMethods`, keeping the selection and non-default values).
The menu handler also terminates parked RT subprocess workers and the warm pool,
whose children imported the pre-reload modules. Still not refreshed: already-placed
Nodz node dialogs and running analyses. Tests: `test_plugin_discovery.py`,
`test_rt_analysis_panel.py::test_reload_rebuilds_kwargs_and_keeps_edits`.

**Recipe execution: how a run advances, fails and stops.** Read this before
touching `executor.py` / `finishedEmits` (2026-09-29 robustness/lag work).
- **Every downstream node start goes through `NodeItem.oneConnectionAtStartIsFinished`**:
  plug signals (wired by `GraphToSignals`), the if/case direct starts, and the
  acquisition node's `MDA_completed` (now via `finishedEmits`). That makes it the
  one place a stopped run is enforced (`flowChart._runAborted`). `ANDlogic_` and
  `scoringEnd_` nodes wait for *every* wired input (`waitsForAllInputs`, counted
  against `n_connect_at_start`); everything else starts on the first. scoringStart
  clears the scoring nodes' `__output__`.
- **`finishedEmits` defers the downstream emit** with `QTimer.singleShot(0)`
  (`_emitNodeFinished`). Inline emits nested every node inside the previous one:
  the GUI froze for a whole multi-position tour and could hit RecursionError. Never
  start the next node synchronously from a node's action; call `finishedEmits`.
- **Pool work goes through `_startNodeWorker(node, type, args, on_success)`**. It
  always reports back, even when the worker raised (`worker.error`) or `on_success`
  raised, and routes failures to `_nodeFailed`: node goes to `error`, the reason goes
  in the Info tooltip, and `_abortRun` runs. Blocking hardware (stage moves, waits)
  goes through `_hardwareThen(node, fn, on_success, label)` onto the owner thread.
  Do not call `core.*` on the GUI thread from a node.
- **Run lifecycle:** `_beginRun(label)` gates all four run buttons (refuses while a
  full run is going). `_abortRun(reason, user_requested)` sets `_runAborted`, clears
  the run flags, cancels the MDA per backend (`core.mda.cancel()` on MMCORE_PLUS,
  `acq.abort()` otherwise, only while `mdaMode`), and sets mid-run nodes to `idle`
  (Interrupt) or `error` (failure). `_advanceToNextPosition` is the single "next
  position or done" step. **Run generation:** each start/stop bumps it; `nodeRan`
  stamps the node, and `_emitNodeFinished` / `_nodeWorkerDone` / `_afterHardware`
  drop a stale node's finish. Without that, a timer or cancelled MDA from a stopped
  run drives the next one.
- **The MDA always reports done.** `mda_acq_done_signal(bool)` carries success; the
  acquisition worker's `finally` reports a failure (`_report_failed_mda`), as do
  both refused-start paths. `claim_mda_done_signal` keeps exactly one listener (each
  acquisition node has its own `MDAGlados`). `MDA_acq_from_Node` refuses while an
  MDA is already running, and always sets `newestLayerName` (default: the node's
  name).
- **`NodeSignalManager` must initialise its QObject once.** A double
  `QObject.__init__` segfaults on free (node delete, recipe reload). All its signals
  are the same class-level `new_signal`, so `emit_all_signals` emits once.
- **Variables UI is debounced.** `nodeRan` schedules one table rebuild per 250 ms
  burst, `updateCoreVariables` keeps at most one snapshot queued, and values show via
  `variableDisplayText`. Node text refresh uses `dontEvaluate=True` and is guarded.
Tests: `tests/test_recipe_*.py`, `test_mda_done_always_fires.py`,
`test_scoring_end_waits_all.py`, `test_mda_finalisation_gate.py`. Open follow-ups:
`docs/plans/claude_issues_and_features.md` ("Recipe execution, deferred").

**MM-config nodes resolve groups by name, live.** `executor.py`'s
`MMconfigChangeRan` branch reads the node's `config_string_storage` (`[group, value]`
pairs) and looks each group up in `mil.get_available_config_groups()` *now*, never
through `node.MMconfigInfo.config_groups`: those `ConfigInfo`s resolve their name
by **list index** (`configGroupName()`), so after the config group editor adds,
removes or renames a group they name a different group or none — which left
`config_group_type` unbound (`UnboundLocalError`). A vanished group is skipped with a
warning; >1 preset → `set_config` + `wait_for_system` (MIL has no `wait_for_config`),
1 preset → write its single property via the MIL `get_config_*` helpers (the old
Java-only `.get(0)`/`get_setting(0)` calls broke other backends).

**The Controls dock's RT-analysis section is `GUI/rt_analysis_panel.py`'s
`RTAnalysisPanel`** (built by `MMConfigUI.realTimeAnalysisLayout`). Full-width
method dropdown; parameters from `utils.layout_init(..., showVariableOptions=False)`
(no Value/Variable/Advanced switch, so every kwarg resolves as a Value) in a
`_ParamsScrollArea` whose size hint is capped at `RT_PARAMS_VISIBLE_ROWS`. That hint
depends on two *other* widgets (the content, the dropdown's row height), so the
area event-filters both and calls `updateGeometry()` -- without it the layout's
cached hint went stale on a method switch or when the dock stylesheet landed. One
toggle button (Activate / highlighted `ROLE_ACTIVE` Deactivate, polled every
`RT_ACTIVE_POLL_MS` because closing the node's layer ends it elsewhere), Reset
(deactivate, then re-activate on a 0 ms timer) and Restore defaults. **Each method runs independently**:
`_runs` maps `Module.Function` to its thread and its *own copy* of the settings,
and the buttons act on the method selected in the dropdown. Never hand the panel's
`currentData` itself to a thread: the node re-reads its class from
`__selectedDropdownEntryRTAnalysis__` every frame (`_rtAnalysisClassName`), so a
second activation would retarget the first. Edits reach a running method by
updating existing keys of its copy (`_onParamEdited`). Running methods are marked in
the dropdown list via item Background/Foreground/Font roles (the combo gets a plain
`QStyledItemDelegate`: the default menu-style popup delegate ignores them), and the
closed combo gets `ROLE_ACTIVE` (green border) while the selected one runs; item
*text* stays the bare display name since methods are looked up by it. Activate with
no live/MDA running also feeds the shown napari image once (selected image layer,
else topmost; never a layer an RT node owns; sliced at the viewer's position).
Non-default values get `ROLE_MODIFIED` and persist in `glados_state.json`'s
`RTAnalysis` section via `appdata.save_state_section` (only differences, so a
changed code default still reaches users) -- only when `autoSaveLoad`, so the Nodz
dialogs' instances never write. `NapariLayerGroup.remove_all` only removes a layer
while the viewer's layer of that name is still the group's own object: the
layer-removed callback defers its sibling sweep, and after a Reset the new node
holds the same names. Tests: `tests/test_rt_analysis_panel.py`.

**Measurement/custom-function dispatch scopes must bind `nodeDict` and `nodzInfo`
by name.** `utils.getFunctionEvalTextFromCurrentData` emits Variable-mode kwargs as
`nodeDict['<node>'].variablesNodz['<var>']['data']` and global ones as
`nodzInfo.globalVariables['<var>']['data']`; the legacy bare `eval` saw both as
locals. Every `registry.dispatch_from_eval_text` scope in `executor.py` splats
`**nodeDict` *and* binds `'nodeDict'` (the splat alone left a Variable-mode kwarg
a `NameError`), and `generalNodzCallActionWorker` receives the flowchart as
`args['nodzInfo']`.

**Node metadata is cached (T-G1).** `__function_metadata__()` rebuilds a fresh
nested dict literal on every call, and the GUI/dispatch path called it several
times *per analysed frame*. Read it through
`autonomous/registry.py`'s `get_metadata(name)` — cached per module **stem**
(`"FFT_im"`; `name` may be the stem or the dotted `Module.Function`), resolved via
a lazy import of `utils._resolve_node_obj`. `utils._node_metadata()` /
`utils._nodeFunctionEntry()` are the in-module wrappers; the returned dict is
shared, so never mutate it. `clear_metadata_cache()` is called by
`reload_all_node_modules()` alongside `_REGISTRY.clear()` — clear it from any new
path that re-imports node modules. `reqKwargsFromFunction` /
`optKwargsFromFunction` / `displayNameFromKwarg` now read that dict directly;
`kwargsFromFunction` still builds its `"key: value"` text blob for other
callers, but nothing per-frame goes through it. Tests:
`tests/test_node_metadata_cache.py`.

**Node code reads the acquisition dimension map through
`utils.getAcquisitionDimensions(shared_data)` (T-G8).** `pSMLM` and `RT_counter`
called `getDimensionsFromAcqData` uncached inside `run()` — a pure-Python walk of
every event in the plan (999 of them in live mode), per frame, holding the GIL,
and touching `_mdaModeParams` also triggers its lazy useq->pycromanager
conversion. The cache is generation-keyed exactly as `_get_cached_dimensions` was
(which now delegates to it) and tolerates `shared_data=None`, which is what a
subprocess-isolated node's `run()` receives. `pSMLM._smlm_frames` also grew one
DataFrame per frame for the whole session; `_append_smlm_frame` compacts them
into one every `SMLM_FRAME_COMPACTION_THRESHOLD` frames — bounding the object
count, never dropping a localization (those are the measurement). Tests:
`tests/test_node_dimension_context.py`.

**RT-analysis dispatch is bound once, not eval'ed per frame (T-G2/T-G3/T-G4).**
`realTimeAnalysis_run` used to rebuild a Python call expression from the kwarg
dict and `eval()` it on *every analysed frame*, and
`realTimeAnalysis_visualisation` did the same on the GUI thread. Now
`utils.buildBoundNode(rt_analysis_info, nodzInfo)` resolves everything once into
a frozen `BoundNode` (className, cached metadata entry, a `BoundKwargs` for
run/end and one for visualise), stashed on the node instance as
`_glados_bound_node`; `run`/`end`/`visualise` are plain method calls with
`bound.kwargs.resolve()` splatted in. Three things to know before touching it:
- **`BoundNode`/`BoundKwargs` must stay dataclasses**, never dict/list/tuple —
  the subprocess worker pickles every attribute of the node instance matching
  `AnalysisClass._SUBPROCESS_SNAPSHOT_TYPES` back to the parent *per frame*, and
  a dict would ship the whole binding with it.
- **Kwarg values are coerced to their declared metadata `"type"` at bind time**,
  permissively (an unconvertible value stays a string, with a warning). Bool
  kwargs therefore arrive as real bools — `LogScale="False"` used to be a truthy
  string. Variable-mode kwargs are closures over the *container* mapping
  (`nodzInfo.globalVariables` / the origin node's `variablesNodz`), re-read on
  every `resolve()`.
- **Editing a parameter mid-run still takes effect.** `currentData` is mutated in
  place by the panel, so `_boundNodeFor` compares `BoundNode.signature`
  (`tuple(rt_analysis_info.items())`) and rebinds when it differs.
The pre-T-G4 eval path and its `GLADOS_RT_EVAL_DISPATCH` escape hatch were
removed in 2026-10. Details and the per-path Value/Variable/Advanced table live
in `docs/developer/rt-analysis-parameters.md` §4. Tests:
`tests/test_rt_kwarg_binding.py`, `tests/test_bound_node_dispatch.py`.

**Node kwarg widgets and the Value/Variable/Advanced switch:** how a node's
`__function_metadata__()` kwargs turn into parameter-panel widgets, how the
per-kwarg Value/Variable/Advanced switch (`name@Origin` / `{name@Origin}`
syntax) is wired, and how to add a new typed widget (e.g. the `QCheckBox` used
for `"type": bool` kwargs) without breaking that switch, is documented in
`docs/developer/rt-analysis-parameters.md`. Read it before
touching kwarg-widget code in `GUI/utils.py`.

**NeNA/FRC exploration (not a node yet)** lives in
`AutonomousMicroscopy/exploration_nena_frc/` — deliberately outside the three auto-imported
folders. `nena_frc_benchmark.py` times candidate implementations per stage (writes
`benchmark_results.md`); `nena_frc_live.py`'s `IncrementalNeNAFRC` is the streaming winner
(additive state: fine NN-distance histogram + persistent windowed FRC canvases, ~65 ms per
1000-frame update on 885k locs). It reproduces **webSMLM**'s conventions (the user's own
browser tool, `github.com/kjamartens/webSMLM`, single `webSMLM.html`): adaptive 4·p25 NeNA
range + unweighted LM Endesfelder fit; FRC random halves x3, Hann, N=2048, 1-2-1 smoothing.
FRC values depend strongly on those conventions (split mode, window, binning kernel) — see
the benchmark's sweep before changing any. Since then the live default deviates from webSMLM
in two FRC-only ways: Gaussian curve smoothing (`frc_smoothing='websmlm'` restores 1-2-1) and
blink merging (`frc_merge_nm=10`, chains of consecutive-frame locs -> mean position, reusing
the NeNA NN search; 0 disables; open chains wait for `finalize()`) — on the test file FRC
goes 24.4 (webSMLM) -> 23.1 (smoothing) -> ~30 nm (merging). **RT node:**
`Real_Time_Analysis/pSMLM_live_precision.py` subclasses `pSMLM_live` and adds a text-overlay
layer (one constant point + napari `text`, so the count never changes) with NeNA, FRC and the
stop flag `n_locs > 2.71/(M*3*pi)/NeNA_um^2*w*h`. `run()` only buffers locs (px -> nm via
`PixelSize_um` metadata, since `core` is None in the child); every `updateEveryNFrames` a
background thread in the subprocess updates the estimator — which is why the numba kernels
in `nena_frc_live.py` are `nogil=True`. Frame numbers prefer MM's `ImageNumber` (counts camera
frames) over `Axes['time']`; a backwards jump restarts the estimator. numba/pyfftw/finufft/pyarrow/scikit-learn were
installed into `.venv` for this but are **not** in `pyproject.toml`.

**Demo recipes for the SMLMDemoCam install** live in
`glados_pycromanager/AutonomousMicroscopy/ExampleRecipes/` (01 simple, 02 intermediate, 03 complex,
04 fun "nuclear pore hunt", plus a 3-plane `.pos`). They are *generated*, not hand-written:
`_generate_demo_recipes.py` boots the real `GladosNodzFlowChart_dockWidget` offscreen (pymmcore-plus core
loading `DemoSMLM.cfg`, stub napari viewer � napari itself needs GL), builds each graph through the app's own
dialogs/helpers and saves with `saveGraph`. Gotchas it works around: `NodeItem.textbox` only exists after a
node has been painted (render the scene before `saveGraph`); `PyQt5.QtWebEngineWidgets` must be imported
before the `QApplication`; decision-widget condition rows are rebuilt on every update, so set them through
`decisionInfoGUIVAR`, not `findChild`. Non-AND nodes start on their *first* incoming connection, so branches
may converge on one node. Brightness thresholds are measured means (camera offset 100: Normal ~100.5,
HighInt ~101, VeryHigh ~103.4 at 50 ms) � a guess-level starting point.

### Path / import conventions

Most modules begin with this shim because the codebase supports both `pip install -e .` and "open the file in an IDE":
```python
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
```
Keep it on new top-level modules under `glados_pycromanager/` if they're meant to be runnable directly.

The shim puts the *repo root* on `sys.path`, not `GUI/`, so a bare sibling import
(`from FlowChart_dockWidgets import ...`, `from utils import ...`) raises
`ModuleNotFoundError` at runtime. Always import package-qualified
(`from glados_pycromanager.GUI.utils import ...`); lazy in-function imports are fine
(and needed where the modules import each other). Beware ones wrapped in
`except ImportError: pass` — `Shared_data.on_warningErrorInfoInfo_changed` silently
never refreshed the node warning/error overview that way.

### Persisted GUI state — `utils.CustomMainWindow.save_state_*`

`save_state_MDA` iterates `vars(self)` and writes every attribute into
`glados_state.json`: a *bare* `QWidget` becomes `{'text':..., 'checked':...}`,
and **everything else is written verbatim** unless its name is in
`self.storingExceptions`. So an attribute holding widgets in a container — a
list, a dict — passes the `isinstance(value, QWidget)` check and then raises
`TypeError: Object of type QWidget is not JSON serializable` inside the encoder.
**Any new attribute on `MDAGlados` that holds widgets, or anything else not
JSON-encodable, must be added to `storingExceptions`** (this bit `_guiWrappers`
from T-F7; today `sectionGrid` and the two `*ListEditor`s are listed). The generic branch now skips un-encodable values with a warning
naming the key and type, and the state is encoded with `json.dumps` *before* the
file is opened — `open(..., 'w')` truncates first, so an encoder failure used to
destroy the user's entire settings file, not just the offending key. Watch the
log for "Not saving MDA state key" and fix the exclusion list rather than leaving
it warning every save. `save_state_MMControls` has no such generic branch (it
stores only values passing the `QWidget` check), which is why the QTimers T-F8
added to `MMConfigUI` are harmless there. Tests:
`tests/test_state_save_widget_attrs.py`.

**The MDA panel's plan rebuild and its state write are both debounced (T-H1).**
Every widget signal goes to `MDAGlados.scheduleMDAEventsUpdate()` (200 ms), never to
`get_MDA_events_from_GUI` directly; each QLineEdit's `editingFinished` flushes it, and
`MDA_acq_from_GUI` / `MDA_acq_from_Node` / `getEvents` call `flushMDAEventsUpdate()`
before reading `self.mda`. **Wire new MDA-panel widgets the same way, and flush in any
new reader of `self.mda`.** `textChanged` is kept on purpose — `setText()` from
`setZStart`/`setZEnd`/the folder picker never emits `editingFinished`, nor does a field
whose validator is `Intermediate`. The rebuild schedules the `glados_state.json` write on
a separate 500 ms timer (`_scheduleMDAStateSave` / `flushMDAStateSave`); both timers are
in `storingExceptions`. Tests: `tests/test_mda_events_debounce.py`.
`MDAGlados.mda` is a **lazy property** (T-H2): `mda_useq` is the plan, the rebuild only
sets `_mda = None`, and the first read runs `to_pycromanager()` and caches. Acquire paths
assign `_mdaEventsForAcquisition()` (the list if already materialised, else the raw
sequence, which `Shared_data._mdaModeParams` converts lazily). Because `vars(self)` shows
`_mda` rather than `mda`, it is in `storingExceptions`, and `nodz_main`'s recipe save skips
`_mda` and writes `mda` explicitly. **Never log `self.mda` with an f-string** — that
forces the conversion. Tests: `tests/test_mda_lazy_events.py`.
The focus device is applied **at acquisition start**, not in the rebuild (T-H3):
`_applyFocusDevice()` (called by both acquire paths after `set_exposure`, before
`mdaMode = True`) sets `z_stage_sel` when `GUI_show_z`, else — or on failure —
`shared_data._defaultFocusDevice`. It reads those attributes, not the widgets, so a Nodz
node's widget-free `mdaData` applies its own stage. Tests:
`tests/test_mda_focus_device_at_acquire.py`.

**Reading it back: never index a section.** The three sections are written by
different code paths at different times, so any of them can be absent — a fresh
install has none, a section appears only once its widgets have been saved, and
`io/appdata.py`'s `save_config_to_json` rebuilds the file with **only**
`GlobalData` when the previous one was unreadable. Use
`gladosInfo.get('MDA', {})`, never `gladosInfo['MDA']`: indexing directly is what
made a truncated state file stop the app booting with `KeyError: 'MMControls'`
(the two MDA loaders had an `except KeyError` fallback, but the section lookup
sat outside it). `appdata.load_glados_state()` is the tolerant reader — missing,
corrupt or non-object content all come back as `{}` with a warning. An unreadable
file is now copied to `glados_state.json.corrupt-<timestamp>` before being
overwritten. Tests: `tests/test_state_file_missing_sections.py`.

### GUI-thread work removed in Tier F

Tier F of the throughput plan is complete. Each item below was work the
GUI thread did repeatedly, competing with the frame path; the mechanism that
replaced it is what new code in these files should follow.

- **Icons (T-F1).** `ui/widgets/builders.py`: `findIconFolder()` is `lru_cache`d
  and rendered icons live in `_ICON_PIXMAP_CACHE`, keyed by
  `(folder, type, alteration, size)`. Both fill **lazily on first use** — a
  `QPixmap` built before a `QApplication` exists is invalid — and a null pixmap
  (missing PNG) is deliberately *not* cached, so the failure stays retryable. Same
  rule applies to `nodz_main.py`'s `_NODE_STATUS_PIXMAP_CACHE`. Tests:
  `tests/test_icon_cache.py`.
- **`NodeItem.paint()` (T-F2).** It no longer touches disk, builds `QFontMetrics`,
  or mutates the model. Status pixmaps, font metrics and text extents come from
  module-level caches (`_nodeStatusPixmap` / `_fontMetrics` / `_textExtent` — the
  last also collapses the two `boundingRect()` calls the original made per string).
  The bottom/top attribute partition became `NodeItem._reorderAttrs()`, called from
  the three sites that change `attrs`: `_createAttribute`, `_deleteAttribute` and
  `Nodz.editAttribute`. **Call it from any new site that mutates `attrs`** — it
  no-ops when the order is already correct. Tests: `tests/test_nodz_paint_caches.py`.
- **Warning updates (T-F4).** `NodeScene.collectWarnings()` builds the list and
  `regular_callAction` assigns it **once** (it used to clear-then-append, four
  writes per tick), and skips the whole check while `liveMode or mdaMode`.
  `Dict_Specific_WarningErrorInfo.__setitem__` no longer takes a full dict copy
  into `oldValue` (nothing reads it; it survives as a `None` class attribute), and
  `_notify_change` coalesces via a dirty flag drained by a zero-delay
  `QTimer.singleShot`. That deferral requires a live `QApplication` **and** the GUI
  thread (`_can_defer_notification`) — a zero-delay `QTimer` needs an event loop in
  the *calling* thread, so off-thread and headless callers are notified inline.
  Note the periodic assignment is also what refreshes the *error* icon, so a
  "skip when unchanged" optimisation here would silently break that. Tests:
  `tests/test_warning_update_coalescing.py`.
- **`checkNodesOnErrors` (T-F5).** `evaluateGraph()` is hoisted out of the per-node
  loop and the loop assigns `node._errorInfo` directly — the public `errorInfo`
  *setter* calls `updateAutonousErrorWarningInfo`, which loops over every node, so
  going through it per node was quadratic. The single refresh after the loop covers
  all of them. The eight graph signals (including `signal_NodeMoved`, which fires
  per mouse-move of a drag) go through `scheduleCheckNodesOnErrors` and a 100 ms
  timer; the six direct callers stay immediate. Watch out: `findConnectedToNode(..., downstream=True)`
  matches the node as connection **destination** (`connection[1]`) — the naming is
  inverted from what it reads like. Tests: `tests/test_node_error_check_batching.py`.
- **Dock relayout (T-F6/T-F7).** `GladosWidget.resizeEvent` now only classifies the
  size (`_layoutForCurrentSize` -> `ui.layout.classify_shape`) and calls
  `_scheduleGroupBoxLayout`, which **drops a layout identical to the applied one**
  and otherwise restarts a 150 ms timer. The replaced `QScrollArea` is
  `deleteLater()`d (one leaked per resize event before) — narrowed to `QScrollArea`
  instances so a live control can never be destroyed. Because a same-size resize is
  now a no-op, a caller whose *widget tree* changed under unchanged geometry must
  call `GladosWidget.requestRelayout()`; that is what replaced
  `MDAGlados.updateGUIwidgets`' synthetic `QEvent.Resize` + `QCoreApplication.processEvents()`
  (which allowed re-entrant `updateGUIwidgets` and could run `napariUpdateLive` slots
  mid-rebuild). The Acquire button is built once — held on `_acquireButton`,
  **not** `GUI_acquire_button`, which starts life as the boolean flag and is passed
  back in as one. Since the UI toolkit, `updateGUIwidgets` builds nothing at all
  (the old per-rebuild wrapper widgets and `_discardPreviousGUIWrappers` are gone):
  it enables sections, refills the order dropdown in place and re-places, and a
  panel with a `sectionGrid` is arranged by `GladosWidget` through
  `ResponsiveGrid.apply` inside a scroll area built once — the reparenting path
  remains only for panels not on the toolkit. Tests:
  `tests/test_dock_relayout_debounce.py`, `tests/test_mda_gui_rebuild.py`.
- **Hardware edits (T-F8, MMcontrols half only).** A slider drag's device write is
  deferred 200 ms (`_scheduleSliderPropertyWrite`) and flushed on `sliderReleased`;
  the GUI half still runs per pixel so the number tracks the handle, and a typed
  value is written straight through. Pending values are keyed per `config_id`.
  Mouse-wheel notches over the z-stage widget *and* over the napari canvas
  accumulate and apply as one relative move of the same total distance, via a
  `steps` multiplier on `moveOneDStage` (default 1). **It is a leading-edge
  throttle, not a debounce** (2026-09-29): the first notch moves at once and the
  notches within the next `STAGE_WHEEL_DEBOUNCE_MS` (120) become one move at the
  window's end (`_lastStageWheelFlush`, same pattern as `rt_replay`'s scrub
  render). The original re-armed a single-shot timer on every notch, so a
  continuous scroll moved the stage *not at all* until the wheel had been still
  for 120 ms — the "z-scroll while live is slow" complaint. `onEditFieldChanged` was
  already on `editingFinished`. **Laser half (approved 2026-09-09):**
  `ChangeIntensityLaserEditField` moved to `editingFinished` — on `textChanged` it
  issued a serial write per keystroke, driving the laser through every partial
  value — and skips a focus-out whose value is unchanged, tracked in
  `ChangeIntensityLaser` because the slider writes through that same choke point.
  The 15 laser-trigger fields deliberately **keep** `textChanged` (the plot is a
  live preview; `editingFinished` would leave it stale) but go through
  `scheduleDrawplot`'s 200 ms debounce. Tests:
  `tests/test_hardware_edit_debounce.py`, `tests/test_mode_setter_no_sleep.py`.
- **Live/MDA toggle (T-F10, part 1).** `acqModeChanged`'s up-to-10 s wait for the
  previous worker no longer runs on the GUI thread: when
  `_worker_stopped_event` is not already set and the caller is the GUI thread,
  `_defer_transition_until_worker_stops()` hands the wait to a daemon thread,
  emits `transition_signals.started` (greying the Live button), and the
  continuation is posted back through the napari bridge to **re-enter
  `acqModeChanged` on the GUI thread** — so every napari and core touch stays on
  the thread it was on. `_acq_transition_lock` and the blocking wait remain: they
  exist because concurrent workers caused a JVM fatal crash, and the blocking wait
  is still the correct path off the GUI thread and headless.
  **Part 2 (approved 2026-09-09, superseding decision item H2):** both
  `time.sleep(0.1)` calls are gone from `on_liveMode_value_change` /
  `on_mdaMode_value_change`. They never made anything synchronous —
  `acqModeChanged` is called synchronously either side of them — so they only
  delayed the dispatch while blocking the flipping thread. The audit found one
  caller that depended on the delay: `MMcontrols.setROI` changes the ROI right
  after stopping live mode and `stop_sequence_acquisition()` is fire-and-forget,
  so its live branch now waits on the core explicitly (stop → wait → set → wait →
  start) and its own `time.sleep(0.5)` is gone. `drawROI`'s pause surrounds a pure
  query and needed nothing — **if it ever grows a `set_roi()`, give it the same
  explicit wait.** Tests: `tests/test_acq_transition_nonblocking.py`,
  `tests/test_mode_setter_no_sleep.py`.
- **Exposure changes restart live mode.** `MMcontrols.py`'s exposure-time field
  (`exposureTimeInputField`) mirrors `setROI`'s live-restart pattern exactly:
  `_onExposureFieldEditingFinished()` (wired to `editingFinished`, replacing a bare
  `storeAllControlValues()` lambda) does nothing extra when `shared_data.liveMode` is
  `False` — the new value is already picked up lazily at the next snap/live-start — and
  otherwise spawns `_exposureChange_liveRestart` on its own daemon thread: stop live,
  wait, `set_exposure`, wait, restart live. Previously editing the exposure field while
  live had no effect on the running acquisition at all. **The restart-to-`True` now
  lives in a `finally`, and the exception list widened from four specific types to bare
  `Exception`** — the original version restarted live only *after* `set_exposure`
  succeeded and only caught `(RuntimeError, OSError, ValueError, AttributeError)`, so
  any other exception (a rejected exposure value, a transient hardware/bridge error)
  left `liveMode` stuck `False` with nothing to auto-restart it — the user had to click
  "Start Live Mode" by hand, which read as the field "crashing" live mode. Now the
  exception is logged with a full traceback (`logging.exception`, for actually
  diagnosing what happened) and live is restarted regardless. Tests:
  `tests/test_mode_setter_no_sleep.py`,
  `tests/test_mmcontrols_owner_thread.py::test_exposure_field_during_live_stops_sets_and_restarts_live`,
  `tests/test_mmcontrols_owner_thread.py::test_exposure_field_restarts_live_even_if_set_exposure_raises`.

### Windows scheduling hints

`observability/process_priority.py`'s `apply_foreground_scheduling_hints()` runs once from
`GUI_napari.main()`: `SetPriorityClass(ABOVE_NORMAL_PRIORITY_CLASS)` plus the EcoQoS opt-out
(`SetProcessInformation(ProcessPowerThrottling, ControlMask=EXECUTION_SPEED, StateMask=0)` —
`StateMask=0` is load-bearing, setting ControlMask alone requests throttling *on*). On a
hybrid CPU Windows otherwise parks an unfocused process on the efficiency cores, which is why
the live display slowed down whenever the napari window was not active. Above-normal rather
than HIGH deliberately: HIGH outranks most of the system and can starve the drivers the
acquisition depends on. Gated by the hidden `performance_config.foreground_scheduling_hints`,
Windows-only, and **entirely best-effort — nothing may depend on it having worked.** Two
ctypes traps are pinned by test because they made the first version a silent no-op:
`GetCurrentProcess()` must be declared `restype = c_void_p` (the `(HANDLE)-1` pseudo-handle is
otherwise truncated on 64-bit, and every call fails with "handle is invalid"), and
`ctypes.get_last_error()` reports 0 unless the DLL was opened `use_last_error=True`, so a real
failure surfaces as `WinError 0`. There is deliberately **no** per-thread priority call: the
old `setPriority(TimeCriticalPriority)` in `AnalysisClass.runAnalysis` was removed, since it
re-set the priority on every image and raised an *analysis* thread above the GUI thread.
Tests: `tests/test_process_priority.py`.

### Logging

`LoggerWidget` (in `GUI/FlowChart_dockWidgets.py`) **tail-follows** its log file
(T-F3): it keeps a byte offset, `seek()`s to it and appends only the delta, and a tick
with nothing new costs a single `stat`. It used to re-read the whole file and
`setPlainText` it every ~500 ms **on the GUI thread**, rebuilding the entire document
layout at a cost that grew with session length — measured 13 ms at a 0.3 MB log, 145 ms
at 7 MB, 486 ms at 22 MB, per tick — which starved napari's frame updates during a long
acquisition. The document is capped at `MAX_LOG_BLOCKS` (5000 lines); the full log stays
on disk. Truncation or rotation resets the offset. Tests:
`tests/test_logger_widget_tail.py`.

**Never launch this app with `-X faulthandler` while a JVM can be in the process.**
HotSpot deliberately raises `EXCEPTION_ACCESS_VIOLATION` during normal operation
(implicit null checks, safepoint polling) and handles them itself; faulthandler's Windows
exception handler runs first, prints "Windows fatal exception: access violation" for each
and dumps every thread, and eventually faults inside `dump_frame` walking a running
thread's frames — killing the process for real. Diagnosed from `hs_err_pid*.log`
("Current thread: JavaThread ... [_thread_in_Java]", "Problematic frame: python313.dll
dump_frame", reached via `faulthandler_exc_handler`). The `Makefile` run targets
therefore default to no faulthandler; `make run FAULTHANDLER=1` opts back in for a
JVM-free debugging run.

`utils.set_up_logger()` writes log files into the AppData directory. Both stdlib `logging` and `loguru` are used; prefer `logging` for consistency with existing code.

RT-analysis nodes that opt into subprocess isolation (`"__runInSubprocess__": True`, see `AnalysisProcess_customFunction` in `GUI/AnalysisClass.py`) run in a `multiprocessing` `spawn`ed child process with its own, separately-initialized root logger — `set_up_logger()`/`set_log_level()` in the main process cannot reach it. The child is given the Adv.-settings log level at spawn time (`log_level` kwarg into `_subprocess_analysis_worker`, applied via `logging.basicConfig`); a later change to the Adv. settings while such a node is running is pushed live through the same `control_in_queue` used for Performance Mode profiling (`__set_log_level__:<LEVEL>` sentinel, sent via `AnalysisProcess_customFunction.update_log_level()`, called from every entry in `shared_data.RTAnalysisQueuesThreads` in `utils.py`'s advanced-settings save handler).

**Subprocess-isolated RT-analysis startup speedups** (fixes a ~20s per-start cost reported for e.g. FFT): a cold `spawn` pays for re-importing the whole `Real_Time_Analysis` package tree plus whatever heavy library the node needs (diplib, tensorflow/stardist, …), and — separately — `AnalysisProcess_customFunction.__init__` used to synchronously build a visualisation "shadow" object on the *GUI thread* via `utils.realTimeAnalysis_init(...)`, freezing the UI for however long that model/weight load took. Two mechanisms now cut this down:

- `GUI/subprocess_pool.py`'s `WarmSubprocessPool` pre-spawns one blank child once startup is ready (`shared_data._rt_subprocess_pool.start()`, in `GUI_napari.main()`'s `_on_startup_ready`; skipped under `--startup-exit`. It used to start right after `Shared_data()`, where the child's imports competed with the GUI build: L2.2 took ready 16.7 → 10.9 s, `tests/test_startup_deferred_pool.py`) that pre-imports the package tree and (best-effort, since it's the only node opted in today) `diplib`, then idles waiting to be handed a real node's `analysisInfo` — shortcutting the first-ever subprocess-node start in a session. **The pool, not the claiming caller, creates the worker's channels** (frame in/out queues, stop event, control pair): a `multiprocessing` Queue/Event can only cross a process boundary by *inheritance*, so they are built in `start()` and passed as `Process` args, and `try_claim()` returns them as a `channels` dict for `AnalysisProcess_customFunction.__init__` to adopt. Sending them through `assign_queue` instead raises `RuntimeError: Queue objects should only be shared between processes through inheritance` on the parent's queue-feeder *thread* — the parent continues unaware while the child blocks forever on `assign_queue.get()`, so the node silently never processes a frame (that was the shipped bug; the cold-spawn path was unaffected, which is why only pool-claimed starts broke). `assign_queue` now carries only `(analysisInfo, log_level)`. Tests: `tests/test_subprocess_pool.py`. Extend its pre-imported-library list (or generalize via an optional `"__prewarm_imports__"` metadata key) if more nodes opt into `__runInSubprocess__`.
- `shared_data._rt_subprocess_cache` (a dict keyed by `AnalysisClass._rt_config_key(analysisInfo)`, a stable hash of the node's config) lets `stop()`/`destroy()` park a still-alive, already-warmed-up worker instead of killing it — `_park_subprocess_worker` handles the cap/idle-timeout eviction opportunistically on each park, no dedicated QTimer needed. A later `__init__` with the identical config reclaims it directly (`_worker_warmed_up = True` immediately, skipping spawn + package-tree import), **but the node itself is still properly closed and reopened, at the times a user would expect** — this is a *process*-level cache, not a node-instance cache: `stop()` sends `{'__close__': True}` on `control_in_queue` immediately when parking (the worker calls `end_fn` right away, so anything it finalises — e.g. flushing/closing a dataset — happens at stop time, never deferred to some future reopen that may not happen), and the *later* reclaiming `__init__` sends `{'__reinit__': True, 'analysisInfo': ...}` to run `init_fn` again (never `end_fn` a second time — that already ran at close). Both are acked on `control_out_queue` (`{'__close_done__': True}` / `{'__reinit_done__': True}`) since there's no ordering guarantee between a control message and a frame put on `in_queue` right after it — see `tests/test_analysis_process.py`'s `test_worker_close_then_reinit_matches_stop_then_reclaim`. **Nothing in the parent reads those acks**, and `control_out_queue` holds 2, so the child sends them with `_ack_nonblocking` (dropped when full): a blocking `put` wedged the worker on the third unread ack, after which a re-activated node never processed a frame ("worker did not respond within 5s"). The reclaim also drains stale acks and stale results (`_drain_queue`), `stop()` drains `in_queue` before parking, and `stop()` is idempotent — `RTAnalysisPanel.deactivate` removes the node's layers, which already tears the node down via `layer_removed_event_callback`, so it now skips its own teardown when the entry is gone (it used to run `end()` a second time). `stop_profiling` skips acks when waiting for its report. Test: `test_worker_survives_repeated_close_reinit_with_unread_acks`. The main-process visualisation shadow is rebuilt fresh on reclaim too, rather than reusing the parked one. So a close→reopen always starts from fresh node state — only the process/imports are reused, meaning a heavy one-time init cost (e.g. model weights) is paid again on every reopen. `AnalysisClass.terminate_all_rt_subprocesses()` is wired into `GUI_napari.py`'s `aboutToQuit` (before the forced `os._exit(0)`) so parked/warm processes don't get orphaned.

**Stopping an RT-analysis node stops its threads (T-G9).** Every RT loop waits
on a `threading.Event` with `RT_THREAD_WAIT_TIMEOUT_S` (1 s) rather than
indefinitely, and every `stop()` **sets** that event after clearing the running
flag — `AnalysisThread_customFunction.stop()` used to clear `is_running` without
waking `run()`, and `destroy()`'s `quit()` only exits a Qt event loop, not an
overridden `run()`, so each start/stop cycle leaked one or two blocked threads
plus their frame deques. `destroy()` now joins with `RT_THREAD_JOIN_TIMEOUT_MS`
(1 s, short because it runs on the GUI thread), logs a warning if the thread did
not exit, and tears the visualisation thread down too. `stop()` is idempotent:
`destroy()` calls it, and both used to run `endAnalysis`, so a node's `end()` ran
twice per teardown. Stop the visualisation thread via its `stop()`, never by
assigning `running = False` — that does not wake it. Tests:
`tests/test_rt_thread_teardown.py`.

**The two RT-analysis loops sleep differently, on purpose (T-G7).**
`AnalysisThread_customFunction._run_loop` keeps
`msleep(max(1, sleepTimeMs, analysis_elapsed_ms))` — sleeping for as long as the
analysis just took is a deliberate GIL-fairness cap, because that compute runs on
that thread in this process. `AnalysisProcess_customFunction._run_loop` sleeps
`max(1, sleepTimeMs)` only: its compute is in another process holding no GIL of
ours and the proxy thread is idle-blocked on `_out_queue.get()` for the whole
round trip, so the same cap merely halved the sustained rate. Don't "unify" them.
Tests: `tests/test_subprocess_proxy_duty_cycle.py`.

**RT-analysis nodes are subprocess-isolated by default (T-G10).**
`utils.realTimeAnalysis_runInSubprocess` answers in this order: the Adv.-settings
global kill switch (`rt_analysis_config.subprocess_isolation`) →
`"__needsLiveCore__": True` (never isolated) → an explicit
`"__runInSubprocess__"` → `RT_SUBPROCESS_ISOLATION_DEFAULT` (now **True**).
`__needsLiveCore__` covers `core`, `shared_data` *and* `nodzInfo`, since
`_subprocess_analysis_worker` passes `None` for all three, and it wins over an
explicit opt-in so a node cannot opt into an isolation it cannot survive.
- Isolated today: `FFT_im`, `SharpnessValue`, `RT_counter`, `pSMLM`,
  `BioImageModelZoo`. In-process by declaration: `LaserAdjustment` (drives the
  laser DAC through the live core), `EndAtFrame` (aborts via
  `shared_data._mdaModeAcqData`).
- **Every shipped node declares one flag explicitly**; the default exists for
  nodes dropped into the AppData plugin folder. Before isolating such a node,
  `nodeRunNeedsLiveContext()` AST-scans its `run()` for attribute access on
  `core`/`shared_data`/`nodzInfo` and leaves it in-process (logging why) if it
  finds any — so an unknown third-party node cannot be silently broken by the
  default. It cannot see indirection, so `__needsLiveCore__` remains the
  supported way to say so.
- Migrating a node means declaring `__snapshot_attrs__` too (T-G5), or its
  overlay silently freezes. `tests/test_subprocess_node_migration.py` enforces
  that statically: every attribute an isolated node's `visualise()` reads that
  its `run()` writes must be declared.
- `subprocess_pool.py` still pre-imports diplib only (it pre-spawns **one** blank
  child, which the first claiming node takes). Generalising that to a
  `"__prewarm_imports__"` metadata key matters more now that five nodes isolate.

**Subprocess state snapshots are opt-in (T-G5).** `.visualise()` needs a live
napari layer, so a subprocess-isolated node runs it against a *shadow* instance
in the main process whose attributes are refreshed from the child after every
frame. That mirror used to be every attribute matching
`AnalysisClass._SUBPROCESS_SNAPSHOT_TYPES` — for `RealTimeFFT` with the taper on,
16.8 MB and 14.2 ms of pickling per frame at 1024x1024, against 8.4 MB / 4.8 ms
once only `fft_display` travels. A node now declares what its `visualise()`
reads, either as `"__snapshot_attrs__": [...]` in its `__function_metadata__`
entry (read once per worker by `utils.realTimeAnalysis_snapshotAttrs`) or as a
`snapshot()` method returning a dict (takes precedence). **Declaring nothing
mirrors nothing** — a new subprocess node whose `visualise()` reads `self.x` must
declare `x`. An attribute the node does not have is skipped rather than mirrored
as `None`, which would clobber the shadow's own value (`firstLayerInit`, set by
`visualise_init()` on the shadow, is exactly that case). Tests:
`tests/test_subprocess_snapshot_optin.py`.

**An RT node may declare several napari layers.** `visualise_init()` still accepts
its historical `(name, type)` 2-tuple, but may instead return a **list** of specs
(`(name, type)` pairs, dicts, or `layer_group.LayerSpec`s with
`name`/`type`/`colormap`/`blending`/`opacity`/`visible`/`scale`/`placement`).
`GUI/layer_group.py`'s `normalise_layer_specs()` reports `(specs, is_legacy)`, and
**`is_legacy` is what decides what `visualise()` receives** - the bare
`napari.layers.Layer` for a legacy 2-tuple (so every pre-existing node is
untouched), a `NapariLayerGroup` otherwise, addressed by name
(`napariLayer['pSMLM: SR render'].data = ...`). It is deliberately *not*
`len(specs) == 1`: a node returning a one-element list has opted in, so adding a
second layer later is not a breaking change to its own `visualise()`. The group
forwards attribute access to its first layer as belt-and-braces, and
`napariOverlay` keeps `self.layer` pointing there for the existing readers.
- **Side-by-side layout is `layer.translate`, not grid mode.** napari's grid mode
  is a global all-or-nothing viewer setting, so it cannot express "these three
  overlaid, that one beside them". A spec's `placement` (`'overlay'` default,
  `'right'`, `'below'`) has the backend compute the offset, so node scripts stay
  layout-free. On napari 0.7.0 `translate` composes *after* `scale`
  (`scale * data + translate`) and is therefore in **world** units - a 10x-upsampled
  SR layer takes the same offset as the raw one - and broadcasts to 0 in leading
  dimensions, so `[0, offset]` works on 2-D and n-D alike. Both facts are pinned
  against real napari layers in `tests/test_layer_group.py`, not just fakes.
  `apply_placement()` no-ops when the base extent has not moved, so the re-offset
  call in `updateVisualisation` is not per-frame work. Note `layer.translate` is an
  **ndarray**, so `getattr(l, 'translate', []) or []` raises "truth value of an
  array is ambiguous".
- **Teardown is group-aware**: closing *any* one of a node's layers tears the node
  down and removes its siblings. `layer_removed_event_callback` and
  `RTAnalysisPanel.deactivate` go through `overlay.group`,
  which also fixes a latent crash - both derefed `napariOverlay.layer.name`
  unguarded, while `napariOverlay` legitimately leaves `.layer` unset when
  constructed with `layer_name=None`. The sibling removal is **deferred**
  (`QTimer.singleShot(0, ...)`): the callback runs on napari's `removing` event, before
  napari deletes the layer by an index it already computed (`remove_selected` deletes a
  whole list of them), so removing siblings synchronously raised `IndexError` inside
  napari's own `__delitem__` (Delete key on a node's layer). Never mutate
  `viewer.layers` synchronously from a `removing`/`removed` handler.
- Note `visualisation_type` in `__function_metadata__` is **dead metadata for RT
  nodes** - its only readers are `autonomous/executor.py`'s two measurement-node
  sites, which are a different visualisation contract entirely
  (`<Module>.<Fn>_visualise(output, napariLayer)` via `dispatch_from_eval_text`,
  never `visualise_init()`). The RT layer type comes solely from `visualise_init()`.
Tests: `tests/test_layer_group.py`, `tests/test_rt_multi_layer.py`.

**An overlay is drawn against the state the frame it shows produced.** The
visualisation payload carries the image *by value* but the node *by reference*, and
the visualisation thread deliberately runs slower than the analysis
(`visualise_delay` plus `visualisation_config.fps`) -- so `run()` normally processes
several more frames, overwriting the node's attributes in place, between a frame
being queued for display and being drawn. The overlay then showed frame N's image
with frame N+k's results, which is what put pSMLM's localizations on a frame they
did not come from. The queued payload now carries that frame's
`state_snapshot` as a 7th element, and
`AnalysisThread_customFunction_Visualisation._visualise_paired` applies it around
the `visualise()` call. Three things to know:
- **The previous values are restored afterwards.** For an in-process node this is
  the *live* instance `run()` is still using, so a node that accumulates in `run()`
  (a counter, a running total) would otherwise be rewound and lose whatever
  happened while the frame sat in the queue. Restored in a `finally`, and a key the
  node did not have is removed rather than left behind.
- **A node that declares no `__snapshot_attrs__` keeps the old, unpaired
  behaviour** -- there is nothing to pair with. Declaring them is what buys
  frame-consistent overlays, which is now a third reason to (after subprocess
  isolation and scrub-replay).
- The subprocess path gets this for free (it already had `state_snapshot` in hand);
  the in-process path builds one per frame and shares it with the replay store.
Tests: `tests/test_rt_visualisation_frame_pairing.py`.

**Points layers must not change length per frame.** napari 0.7 slices
asynchronously and Glados sets `NAPARI_ASYNC=1`, so a slice response computed for
one point list can arrive after a different one has been assigned; napari then
indexes the new `shown` array with the old response's indices and raises
`IndexError: index N is out of bounds for axis 0 with size N` from
`Points._update_slice_response`/`_view_data`, on its own thread where it cannot be
caught. `pSMLM_live._push_points` is the pattern: a **fixed-capacity buffer** with
`shown` masking the unused rows, so a stale index is always in range however late
the response is. The buffer only ever grows (shrinking reintroduces the same length
change; the memory is two floats per slot), grows geometrically, and parks surplus
rows on the first real localization so a response that briefly renders them
unmasked shows nothing stray. Reducing the *number* of layer-property assignments
per frame (style once, assign `data` last) makes it rarer but does **not** remove
the trigger -- only the constant length does. `pSMLM.py` still has the old pattern;
see `docs/plans/claude_issues_and_features.md`.

**RT results are retained and replayed while scrubbing a finished acquisition.**
Dragging napari's time/z slider used to move the image but leave every RT overlay
frozen on the last analysed frame. `GUI/rt_history.py` (the store, Qt-free) and
`GUI/rt_replay.py` (`RTReplayController`, GUI-thread) now re-render each node's
overlay for the frame you land on, calling the node's own unmodified `visualise()`.
- **The stored unit is the T-G5 snapshot**, keyed by `axes_key(metadata['Axes'])`.
  That dict already is "the state `visualise()` needs for this frame", which is why
  no node script had to change. The **raw frame is not stored** - replay re-reads it
  from `shared_data.mdaZarrData[layerName]`, which already holds every frame
  uncompressed at one frame per chunk.
- **`utils.realTimeAnalysis_replayable()`** decides participation: an explicit
  `"__replayable__"` wins; else True iff the node declares `__snapshot_attrs__` or a
  `snapshot()` method; else False. Every *shipped* node declares it explicitly
  (`tests/test_rt_replay_recording.py` pins all eight); the default exists for
  AppData plugin-folder nodes. A node that **accumulates inside `visualise()`** must
  declare False - replaying an arbitrary frame corrupts the accumulation rather than
  re-rendering it (`pSMLM_image`). Full-frame-output nodes (`FFT_im`,
  `BioImageModelZoo`) are False on memory grounds: `fft_display` is a full
  camera-frame float64 - 2 MB at 512 sq., 8 MB at 1024 sq. - not the 512x512
  placeholder its `__init__` suggests.
- **In-process snapshots are references, not copies.** `_build_state_snapshot`
  stores `snapshot[name] = value` bare, so a node reusing a buffer would rewrite
  every history entry it ever made. `RTNodeHistory.record` copies every ndarray; the
  subprocess path gets copies free via unpickling.
- **Invalidation is a generation stamp, not a clear-at-start.** Entries carry
  `_mdaModeParamsGeneration` and a mismatch reads as a miss, so old results can never
  be replayed onto a new plan - and it is independent of teardown ordering (clearing
  at acquisition start would race the RT threads, which are created before the zarr
  exists).
- **The session outlives the analysis thread**, which is the whole point:
  `create_real_time_analysis_thread` connects `finished` to `deleteLater` and the
  node instance is only reachable through the thread. `shared_data.rt_replay` holds
  the node, its `group` and its history. The layers already survived -
  `MDA_acq_finished` calls `stop()`, not `destroy()`. The one release point is the
  user closing the overlay. A reclaimed warm subprocess worker brings back the *same*
  shadow instance, so its session is retired on reclaim rather than aliasing a live
  run with stale history.
- **Replay is inert while `liveMode or mdaMode`** - the display path drives
  `dims.set_current_step` itself, once per frame, and owns those layers.
- **A history miss re-analyses on demand**, off the GUI thread, latest-request-wins,
  marshalling back through the napari bridge; the result is stored so a second visit
  is a cache hit. It runs against a **throwaway node instance**, never the
  acquisition's own - `run()` accumulates (pSMLM appends every analysed frame to its
  localization table), so re-running the acquisition's instance while scrubbing would
  corrupt the results it produced.
- **No searchsorted is needed for the frame read**: the display path sets
  `current_step` *to* the searchsorted indices, so `current_step[:k]` already is the
  zarr slice index. Only the history key needs the inverse value lookup
  (`axes_from_current_step`, round-trip tested against the display path).
- Settings: `rt_analysis_config.replay_history_budget_mb` (256, shared across nodes,
  drop-oldest, warns **once** not per frame) and `replay_debounce_ms` (120, hidden).
- Note history only ever holds *analysed* frames: `put_data_in_visualisation_and_analysis_queues`
  drops a frame for any node still busy with the previous one, so gaps are normal -
  which is what the on-demand re-analysis above exists for.
Tests: `tests/test_rt_history.py`, `tests/test_rt_replay_recording.py`,
`tests/test_rt_replay_controller.py`.

**`pSMLM_live` is the reference node for both features above**
(`Real_Time_Analysis/pSMLM_live.py`): three layers - the frame its own `run()`
analysed, its localizations, and an SR render placed `'right'`. **The SR panel is
refreshed on a `SR_REFRESH_INTERVAL_S` (0.5 s) timer, not per frame, and refreshed
*in place***: at 256x256 the canvas is 26 MB (200x a camera frame), and the
`_sr_version` guard alone never held during an acquisition because `_sr_version` is
bumped on every frame that has any localization - so the whole array went to napari
at the overlay's rate, on the GUI thread. Being cumulative it carries no per-frame
information, so lagging up to that interval costs nothing; the localization and
analysed-frame layers still update every frame. `.data` is assigned only when napari
holds a *different* object (first push, or after `_ensure_canvas` reallocates),
keyed on identity so a reallocation cannot be missed; otherwise `refresh()`.
The analysed-frame layer uses the live path's `data[:] = image; refresh()` idiom.
Note **the `_push_points` buffer is deliberately re-allocated per frame**: napari's
`Points._set_data` keeps the array by reference and its data event hands that same
object to listeners, so a reused buffer would show them a later frame's
coordinates - and the saving would be ~16 KB against a 26 MB push. Showing the
*analysed* frame is the answer to "my localizations are always one frame behind",
and costs no snapshot attribute because `visualise()` already receives that frame as
its `image` argument (both producers pass on the frame they fed to `run()`). Its SR
canvas accumulates in `visualise()`, not `run()`, because the canvas is the frame
upsampled 10x per axis - 25 MB at 256 sq., 100 MB at 512 sq., 400 MB at 1024 sq. -
and a `run()`-built attribute would be snapshotted and shipped across the subprocess
boundary *per frame*. The price is that the SR panel is cumulative and does not
rewind while scrubbing, whereas the other two layers replay exactly; a set of
already-stamped frame keys stops a revisited frame being counted twice. Tests:
`tests/test_psmlm_live_node.py`.

**diplib import gotcha in `spawn`ed subprocesses (IPython inputhook):** if `'IPython'` is already in `sys.modules` in a subprocess (e.g. the app was launched from an IPython/Jupyter shell, or another import pulled IPython in) but `IPython.terminal.pt_inputhooks` hasn't itself been imported yet, `import diplib` raises `AttributeError: module 'IPython.terminal' has no attribute 'pt_inputhooks'` — modern IPython (9.x) only sets `pt_inputhooks` as an attribute of `IPython.terminal` once that submodule has actually been imported, but `diplib/viewer.py` (`from . import viewer` inside `diplib/__init__.py`) assumes it's already there whenever `'IPython' in sys.modules`. Both `subprocess_pool.py`'s pre-warm bootstrap and `FFT_im.py`'s `RealTimeFFT.__init__` work around it by doing `import IPython.terminal.pt_inputhooks` first when `'IPython' in sys.modules`, before `import diplib`. Apply the same guard to any new node that imports diplib in a subprocess-isolated context.

## "Optimize performance of gladoscopy on runtime" protocol

When the user asks to **optimize (runtime) performance of gladoscopy** (or any close
variant), start by measuring with this exact method, before changing code, and re-run it
after each change to compare:

```
.venv/Scripts/python.exe -m glados_pycromanager.GUI.GUI_napari --backend "Python" \
  --config "C:/Users/kjamartens/AppData/Local/pymmcore-plus/pymmcore-plus/mm/insiliscope.cfg" \
  --mm-path "C:/Users/kjamartens/AppData/Local/pymmcore-plus/pymmcore-plus/mm/Micro-Manager_2.0.3_20260724" \
  --buffer-mb 4096 --max-memory-mb 12000 --profile-runtime 15 > "$TEMP/claude_run.log" 2>&1
```

(Same backend/config as `make run-demo-smlm` / `demo_settings.mk`, plus `--profile-runtime`.)
It opens the GUI, sets exposure to 50 ms, runs live mode for 15 s, stops and closes itself
(no user interaction needed); give the Bash call a ~5 min timeout. Each run **appends** to
`docs/perf-runtime.txt` (record `wc -l` first and read only the new tail): a header naming
the real source (`--backend … --config …`), the **per-thread CPU** table
(`format_report_text`), then the cProfile top-25. Read:
- Run log: `continuous sequence acquisition stopped after N frames (M camera frames
  consumed…)` → pulled vs. camera frames (N, M / 15 s).
- `napariUpdateLive calls observed: N` → displayed fps.
- **Per-thread CPU is the trustworthy number; cProfile's cumulative times are not across
  threads.** In Python 3.13 cProfile records every thread and charges time spent waiting /
  on other threads to whatever the profiled thread had on its stack (`pull_once` once showed
  16.9 s cumulative in a 15 s window; `paintGL` "25 ms" was ~1 ms of real callees). Use
  call *counts* from it, and `pstats` callee breakdowns for single-thread questions.
- Run-to-run noise is large (camera 219-268 frames at identical settings), because the
  inSiliScope camera simulates **in-process on the same laptop CPU + Iris Xe GPU**. Compare
  A/B with >= 2 runs each. For a flag-free A/B, run through a tiny `runpy` launcher that
  monkeypatches the one thing being compared before `runpy.run_module(...GUI_napari)`.
- **inSiliScope's `General_AcqMode=Live` costs ~64-88 % of a core while idle** (continuous
  simulation, on the GPU when `General_UseGpu=On`); `Precomputed` idles at ~2 %. Measured with
  bare pymmcore, no Glados. Subtract it before blaming Glados for idle load; a bare napari
  viewer idles at ~2 %.
- Deeper tools that worked: a `QApplication.exec_` wrapper (static in PyQt5 — call it with no
  `self`) installing an event-counting `eventFilter` for idle event rates. Did **not** work:
  `py-spy --native` on Windows (falls behind / no Qt symbols); attach to the *child* PID, the
  `.venv` `python.exe` is a launcher (`--subprocesses` refuses `--native` on Windows).

Baseline (2026-09-29, i7-1355U laptop, Iris Xe, 16 GB, 256x256 uint16): camera 268 frames
(~18 fps), displayed 115 (~7.7 fps); `pull_once` 5595 calls (0.5 ms `LIVE_SEQUENCE_POLL_S`
idle sleep → busy-poll holding the GIL); `_on_slice_ready` ~24 ms per displayed frame.
After `LivePollPacer` + `FastImage` (same day): ~600-750 polls (~2.5-3/frame), owner thread
~0.7 s CPU/15 s (was ~2 s), displayed 125-127, `_on_slice_ready` gone from the profile,
Glados display work ~3 ms/frame; GUI thread still 57-74 % CPU, mostly native (Qt/driver),
with the simulator above competing for the same CPU/GPU.

## Documentation

The documentation is a MkDocs Material site built from `docs/` (`mkdocs.yml`; set up like
the inSiliScope repo's) and published to <https://kjamartens.github.io/Gladoscopy/> by
`.github/workflows/pages.yml` on push to `main` (one-time: Settings → Pages → Source:
GitHub Actions). Pages: `index.md`, `installation.md`, `user-guide/` (controls, mda,
autonomous, troubleshooting), `developer/` (writing-nodes, rt-analysis-parameters, api,
contributing — a `pymdownx.snippets` include of the root `CONTRIBUTING.md`), `module-map.md`,
`adr/`, `changelog.md` (includes `CHANGELOG.md`). Images are in `docs/img/`.
- `developer/api.md` is generated by **mkdocstrings** (griffe *static* analysis — nothing is
  imported, so CI installs only mkdocs). A package folder without `__init__.py` cannot be
  collected (that is how `Core/` turned out to be missing from the wheel).
- `make docs` builds with `--strict` (a broken link or a docstring griffe cannot parse fails
  the build); `make docs-serve` previews. The `docs` extra is part of `make dev`.
- Not published: `docs/plans/` (archived planning docs and decision logs) and `docs/*.txt`
  (appended perf logs) via `exclude_docs`; the engineering notes `bench-live-display.md`,
  `perf-runtime-recipe.md`, `lazy-import-strategy.md` build but are `not_in_nav`.
- In-app help (the Controls **Help** box, the napari *Open the Glados user manual* command)
  opens the site: `glados_pycromanager/docs_links.py` holds `DOCS_URL` and the page paths.
  Keep those paths in sync when renaming pages.

### Keep this file current

Whenever you explore code in this repo and find a module, pattern, or behavior that isn't captured above, add a concise note to the relevant section here (or a new section if none fits) before finishing the task — don't wait to be asked. This applies any time it happens, not just during the optimization plan. Keep additions terse and factual (what/where/why-it-matters), matching the style already used above; prefer extending an existing bullet over adding a new subsection when the topic already has a home. The goal is for each session to leave this file slightly more complete than it found it, so future sessions ramp up faster.

## Archived plans

The 2026 optimization work (`claude_project.md`, `claude_throughput_project.md`,
`claude_launcher_project.md`) and its decision and issue logs (`claude_decisions.md`,
`claude_issues_and_features.md`) are archived in `docs/plans/`. Task IDs in the notes in
this file (T-B3, L2.4, …) refer to those plans. Look there for "why was it done this way?".

## Launcher and startup

- **One-click launch (L1).** `gladosw.exe` (`[project.gui-scripts]`, pythonw) → `GUI/startup.py:main`.
  Before the splash, `main` does three things:
  - redirects pythonw's `None` stdout/stderr to `<AppData>/Glados-PycroManager/Glados_console.log`
    (a per-pid file if a running instance holds it);
  - sets the AppUserModelID `Glados.Pycromanager`, the same one written on the main
    "Glados" `.lnk`, so the window groups under the pinned icon. The other two shortcuts
    get `.LastSetup`/`.DebugConsole` suffixes: the Start Menu lists apps **by AUMID**, so
    shortcuts sharing one collapse into a single entry (check with `Get-StartApps`);
  - runs the per-user single-instance check (`GUI/single_instance.py`, a `QLocalServer`).
    The second launch calls `AllowSetForegroundWindow(<first pid>)` because only it owns
    the foreground. `--allow-second-instance` bypasses the check.

  A fatal startup error on a console-less launch shows "Glados could not start"
  (`_show_fatal_startup_error`): "Show Details..." holds the console log's last
  `LOG_TAIL_LINES` lines, "Open log file" opens it, and the box re-`exec_`s until OK.
  Micro-Manager's own start error is what it should show: the start-dialog path used to
  swallow `start_headless()`'s exception, so `Core()` failed next with pycromanager's
  generic "Is the ZMQ server on 4827 enabled?". `connect_headless_core(Core, start_error)`
  now raises `MicroManagerStartError` carrying the real cause (connection error chained).

  Related pieces:
  - Shortcuts: `make shortcuts` (`glados_pycromanager/shortcuts.py`). Windows 11 can't pin
    from code; the user pins the Start Menu entry. "Glados (debug console)" targets
    `cmd.exe /k "<glados.exe>"` (not `glados.exe` itself) so the console outlives a crash or
    `os._exit`; `ShortcutSpec.launcher` is the venv script `install` checks for.
  - `--last` (`GUI_napari.resolve_last_setup`) skips the dialog using the saved backend and
    config, or falls back to the dialog.
  - `make dev` stamps a pyproject fingerprint into the venv (`install_check.py`); a mismatch
    shows a napari warning at startup-ready.
  - Console-less startup crashes go to a message box naming the console log.
  - The JAVA bridge spells config settings `get_setting` (snake_case), hence
    `MIL._config_setting`. Tests: `tests/test_launcher.py`.
- **Startup timeline.** `observability/startup_timeline.mark(label)` stamps a startup stage,
  timed from **process creation** (psutil). `GUI_napari.py` imports it before every heavy
  import, which is why the `sys.path` shim now sits above `import pymmcore`.
  `napariGlados.call_when_startup_ready(fn)` runs once on the first idle turn after
  `_sizeControlsDock` ("ready"); the full table is logged at INFO then. `--startup-exit`
  (popup-free launches only) appends the table to `docs/perf-startup.txt` and quits;
  `make profile-startup-full` runs 3× per backend and appends medians (~2.3 min). Baseline
  2026-10-13: ready at ~23 s warm (PyMMCorePlus demo), ~60 s cold. The Controls dock alone
  takes 6.5–7.7 s warm. Tests: `tests/test_startup_timeline.py`.
- **Startup splash / light entry point.** Every launch path goes through
  `GUI/startup.py:main`:
  - the console scripts point at it, and `GUI_napari.py`'s `if __name__ == '__main__'`
    branch delegates to it **before** its own heavy imports.
  It imports pymmcore → PyQt5, creates the app's **only** `QApplication` (attributes via
  `set_qt_application_attributes()`), shows `GUI/startup_splash.StartupSplash`, and then
  calls `GUI_napari.main(app=, splash=)`.
  - The backend dialog runs in a local `QEventLoop` on that app (`headlessGUI.closed`).
    `appSmall` is gone.
  - The splash follows timeline marks by **label** (`STEP_AFTER_MARK`; a test pins every key
    to a real `mark(...)`), so renaming a mark needs the map updated.
  - It processes events only while `pump` is True (until `thread.start()` in `main()`) and
    only repaints after that, so queued slots never run re-entrantly mid-dock-build.
  - It is deliberately **not** stay-on-top: a one-shot Win32 topmost/not-topmost raise, then
    owned by napari's window from the `'napari viewer created'` mark.
  - Image: `Icons/GladosSplash_720.png`, regenerated by `scripts/make_splash_images.py`
    from the 4372 px `GladosSplash_inv.png`; the backend dialog uses it too.
  - Tests: `tests/test_startup_splash.py`. A test that creates a `QApplication` must set
    `AA_ShareOpenGLContexts` first, or a later napariGlados import (QtWebEngine) fails.
- **Node packages must import light** (`tests/test_node_packages_import_light.py`). The
  Controls dock imports every node module during startup. `BioImageModelZoo.py`'s
  module-scope bioimageio patches (→ torch) plus module-scope `scipy.signal` made that dock
  the largest startup step (6.5–7.7 s warm → ~3 s). They now run via
  `_ensure_bioimageio_patched()` on first use. `scipy.signal` is **not** exempt from the
  lazy-import rule.
- **pycromanager, ndtiff, dask.array and pandas load on first use (L2.3, PyMMCorePlus
  ready 13.6 → 11.6 s).** `pycromanager` (~2.7 s, nearly all `ndstorage → dask.array →
  xarray → pandas`) was imported by MIL, `napariGlados` and `MDAGlados` at module scope.
  Now:
  - MIL resolves `PycroManagerCore`/`JavaObject`/`multi_d_acquisition_events` through a
    module `__getattr__`. Backend detection uses `_pycromanager_type()`, which returns
    None while pycromanager is unimported: a pycromanager core can't exist before then.
  - `MDAGlados.__init__` stores its initial plan's arguments in
    `_pendingInitialMDAKwargs`; the `mda` property builds it on first read, and a
    rebuild or assignment drops it. The attribute is in both persistence skip lists.
  - The acquisition worker gets `HardwareControlException` via
    `_pycromanager_hardware_control_exception()`, so the first Live click on
    PyMMCorePlus doesn't import pycromanager either.
  - Node metadata names `ndtiff.NDTiffDataset` as a port type and **plugin discovery
    calls every `__function_metadata__()` at startup**, so nodes and the Autonomous dock
    use `glados_pycromanager.lazy_imports.ndtiff`. Its `NDTiffDataset` is a lazy class
    tag: a real `type` that equals the real class and defers `isinstance`/calls/
    attributes to it.

  Tests: `tests/test_lazy_pycromanager.py`, and
  `test_node_packages_import_light.py::test_startup_modules_do_not_import_pycromanager_or_dask`.
  To see who imports what at startup, a meta-path finder that records the stack on a
  module's first import is quicker than reading `-X importtime`, which only shows the
  first importer's chain.
- **napari's own startup costs (L2.4).**
  - **pint's unit registry** is first built by the scale bar, and the build parses pint's
    definitions file (0.8 s). `napariHelperFunctions.use_cached_unit_registry()` (called
    by `showScaleBar`) installs a lazy registry that uses pint's disk cache (0.05 s once
    written; the first launch ever pays ~1.2 s to write it). It changes nothing once the
    registry is built, since swapping it then would split quantities across registries.
  - **napari saves its whole settings file each time a dock's area is recorded**
    (`_update_default_dock_area`): 8 saves, ~0.5 s. `_suspend_napari_settings_saves()`
    runs just before `napari.Viewer()` and `_sizeControlsDock` resumes it, which does
    one save.
  - **Creating the viewer hidden is no gain** (A/B: ready −0.17 s, noise). The canvas's
    *first* GL paint costs ~2 s wherever it happens; hiding the window only moved it from
    the Controls step to the final one.
  - Tests: `tests/test_startup_napari_costs.py`.
- **The circular buffer is allocated on the owner thread (L2.5).** A 4096 MB
  `setCircularBufferMemoryFootprint` commits the memory (~1.75 s; pymmcore mostly releases
  the GIL) and was the whole PyMMCorePlus "backend up" step. `GUI_napari._allocate_circular_buffer`
  queues `MIL.set_circular_buffer_memory_footprint` (hardware-locked) as the MicroscopeService's
  first job; the Python backend starts headless with `HEADLESS_PLACEHOLDER_BUFFER_MB` (64)
  and gets its size the same way. JAVA allocates in the JVM and is unchanged. It is safe
  because the queue is FIFO and nothing can queue an acquisition before the GUI exists,
  and a direct MIL call waits on the lock. **The GUI build's first hardware read
  (`get_focus_device`) therefore sits after `InitateNapariUI`**: before the viewer it
  blocked the GUI thread for the whole allocation and the overlap was zero. Gain: post-import
  startup −1.5 s (PyMMCorePlus), −0.6 s (Python). Tests: `tests/test_startup_circular_buffer.py`.
- **`insiliscope.cfg` + Python backend segfaults in `start_headless`** (2026-10-13), even in a
  bare pycromanager script, while `MMConfig_demo.cfg` in the same install is fine. So the
  documented `--profile-runtime` command currently crashes there. The cause is the
  inSiliScope adapter or its environment, not Glados.
