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
  hardware, block on I/O, or run analysis. Anything else belongs on a worker. **Tier F of
  `claude_throughput_project.md` is complete** — both halves, including the two decision
  gates the user approved on 2026-09-09 — and removed the standing violations it named;
  see *GUI-thread work removed in Tier F* below. **T-B4 removed the
  `LaserControlScripts.py` half**: every hardware touch in that file goes through
  `submitHardware()`, which queues onto the T-B3 owner thread (and runs inline when no
  service is running, so the plugin path and the tests are unaffected). The three slots
  that hurt — `ResetLasersTrigger` (~100 serial round trips per click), `armLaser`
  (0.1 s of sleep per repeat frame, x5 lasers via `armLaserTriggering`) and `blinkUV`
  (sleeps between its on and off writes) — are queued whole, with widget *reads* done on
  the caller first and widget *writes* marshalled back through
  `_onGuiThread` (the `NapariBridge`). Two behaviour notes: `TS_Response_verbose` made
  three identical `get_property` reads to display one answer and now makes one, and
  `_refreshLaserButtonLabels`/`_applyLaserButtonLabels` split the five on/off reads from
  the label writes (the reset loop refreshes once at the end instead of ten times
  mid-loop). Tests: `tests/test_laser_controls_owner_thread.py`, which pins the emitted
  serial command sequence so the refactor stays observationally identical at the wire.
  **`FlowChart_dockWidgets` followed**: `updateCoreVariables` (which the plan
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
    mode) is a single queued job.
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
  decorator to every public method that touches `self.core` (53 applications today). Re-entrant
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
pixel-size caches). Nothing calls them yet — T-C3 of `claude_throughput_project.md`
replaces the 999-frame-MDA live loop with them.

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
  `self.config_groups` + every row from scratch). `updateConfigsFromMM()`
  (the previous single mechanism, still used nowhere else) only pushed new
  *values* into already-existing row widgets — a dropdown's item list and
  the row count itself were frozen at construction, so a group added,
  renamed, or given a new preset via the config group editor could never
  appear, and refreshing an existing dropdown to a preset name that didn't
  exist yet at construction silently did nothing (`QComboBox.setCurrentText`
  on a non-matching string is a no-op). The "Refresh configs from MM"
  button, `updateAllMMinfo()`, and `openConfigGroupEditor()`'s post-dialog
  refresh all now call `rebuildConfigLayout()`.
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
`tests/test_layer_shape_validation_cache.py`.

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
logs at INFO, where `np.append` raised. Tests: `tests/test_album_layer_growth.py`.

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
The cost of that decision is one file per frame (see `claude_issues.md`).

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
default buffers the whole acquisition in RAM until close -- see `claude_decisions.md`
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

`Shared_data` is the single object passed everywhere (UI, worker threads, napari plugins, autonomous microscopy nodes). It holds `core`, the MIL instance, config dataclasses, analysis-thread lists (`LoggingList` is a list subclass that emits Qt signals on mutation), and live/acquisition state flags. When adding cross-component state, add it as a field on `Shared_data` rather than a global.

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

- `GUI_napari.py` — standalone entry. Builds a `headlessGUI` for backend choice, spawns Napari, runs `runNapariPycroManager` in a `Worker`/`QThread`. Sets `NAPARI_ASYNC=1` and `NAPARI_OCTREE=1` *before* importing napari.
- `_dock_widget.py` — napari plugin entry. `MainWidget` constructs `Shared_data`, calls `pycromanager.Core()` directly, and adds four dock widgets — all of which inherit `GladosWidget`:
  - `MMConfigWidget` — Micro-Manager config groups, stages, ROI (`microManagerControlsUI_plugin`)
  - `MDAWidget` — Multi-D acquisition (`MDAGlados_plugin`)
  - `AutonomousMicroscopyWidget` — recipe graph (`autonomousMicroscopy_plugin`)
  - `GladosSlidersWidget` — laser controls (`gladosSliders_plugin`)
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
  - **Live/MDA stop→start race guard:** `napariHandler_liveMode`/`napariHandler_mdaMode` are constructed once per session and reused for every toggle, so rapid Live/MDA on-off-on toggling could previously start a new `run_MILCoreAcquisition_worker` (QThreadPool job) while the old one was still tearing down the same `core.mda`/`Acquisition` object (`stop_sequence_acquisition()` is fire-and-forget) — two threads driving the same native MMCore/Java engine concurrently, causing native access violations under stress testing. `napariHandler` now has `_acq_transition_lock` (an `RLock`, since the worker's own cleanup re-enters `acqModeChanged` from its own thread) and `_worker_stopped_event`: `acqModeChanged`'s ON path waits (`ACQ_STOP_TIMEOUT_S`, default 10s) for the previous worker to fully exit before starting a new one, refusing to start (and reverting the mode flag) rather than racing if the timeout is hit.
  - **Frame ring (MMCORE_PLUS `frameReady` path):** `grab_image_liveVis_PyMMCore` is connected with `Qt.DirectConnection`, so it runs synchronously on pymmcore-plus' own MDA thread — everything it does happens in front of the next camera frame. It is therefore a pure hand-off: `frame_ring.push(image, metadata)` and return. `GUI/frame_ring.py`'s `FrameRing` is a bounded, overwrite-oldest, stdlib-only buffer (drop-counting, with an `Event` the consumer waits on); `napariHandler._frame_ring_consumer_loop` (a plain daemon `Thread`, started just before the `frameReady` connect and stopped just after the disconnect, plus an idempotent stop in the acquisition worker's outer `finally`) does the real per-frame work: `metadata_refactor`, the multiDstack zarr write, and `put_data_in_visualisation_and_analysis_queues`. Two capacities: `FRAME_RING_CAPACITY_DISPLAY` (4) for live, since display and RT analysis drop frames at their own gate anyway, and `FRAME_RING_CAPACITY_STORAGE` (256) for multiDstack MDA, where a dropped frame is a permanently black slice with no NDTiff store to backfill from. The per-acquisition drop tally is logged at teardown (WARNING if non-zero). The pycromanager `image_process_fn` / `image_saved_fn` paths do **not** use the ring — `image_process_fn` must return `(image, metadata)` synchronously for pycromanager to store the frame.
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
`GLADOS_RT_EVAL_DISPATCH=1` restores the pre-T-G4 eval path
(`_realTimeAnalysis_*_viaEval`) for one release as an escape hatch. Details and
the per-path Value/Variable/Advanced table live in
`Documentation/rt_analysis_parameters.md` §4. Tests:
`tests/test_rt_kwarg_binding.py`, `tests/test_bound_node_dispatch.py`.

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

### Persisted GUI state — `utils.CustomMainWindow.save_state_*`

`save_state_MDA` iterates `vars(self)` and writes every attribute into
`glados_state.json`: a *bare* `QWidget` becomes `{'text':..., 'checked':...}`,
and **everything else is written verbatim** unless its name is in
`self.storingExceptions`. So an attribute holding widgets in a container — a
list, a dict — passes the `isinstance(value, QWidget)` check and then raises
`TypeError: Object of type QWidget is not JSON serializable` inside the encoder.
**Any new attribute on `MDAGlados` that holds widgets, or anything else not
JSON-encodable, must be added to `storingExceptions`** (this bit `_guiWrappers`
from T-F7). The generic branch now skips un-encodable values with a warning
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

Tier F of `claude_throughput_project.md` is complete. Each item below was work the
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
  size (`_layoutForCurrentSize`, four aspect-ratio buckets) and calls
  `_scheduleGroupBoxLayout`, which **drops a layout identical to the applied one**
  and otherwise restarts a 150 ms timer. The replaced `QScrollArea` is
  `deleteLater()`d (one leaked per resize event before) — narrowed to `QScrollArea`
  instances so a live control can never be destroyed. Because a same-size resize is
  now a no-op, a caller whose *widget tree* changed under unchanged geometry must
  call `GladosWidget.requestRelayout()`; that is what replaced
  `MDAGlados.updateGUIwidgets`' synthetic `QEvent.Resize` + `QCoreApplication.processEvents()`
  (which allowed re-entrant `updateGUIwidgets` and could run `napariUpdateLive` slots
  mid-rebuild). `updateGUIwidgets` also reuses one Acquire button — held on
  `_acquireButton`, **not** `GUI_acquire_button`, which starts life as the boolean
  flag and is passed back in as one — and discards the previous rebuild's wrapper
  widgets instead of stacking them in the same grid cells. Tests:
  `tests/test_dock_relayout_debounce.py`, `tests/test_mda_gui_rebuild.py`.
- **Hardware edits (T-F8, MMcontrols half only).** A slider drag's device write is
  deferred 200 ms (`_scheduleSliderPropertyWrite`) and flushed on `sliderReleased`;
  the GUI half still runs per pixel so the number tracks the handle, and a typed
  value is written straight through. Pending values are keyed per `config_id`.
  Mouse-wheel notches over the z-stage widget *and* over the napari canvas
  accumulate and apply as one relative move of the same total distance, via a
  `steps` multiplier on `moveOneDStage` (default 1). `onEditFieldChanged` was
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
  live had no effect on the running acquisition at all. Tests:
  `tests/test_mode_setter_no_sleep.py`.

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

- `GUI/subprocess_pool.py`'s `WarmSubprocessPool` pre-spawns one blank child at app startup (`shared_data._rt_subprocess_pool.start()`, called right after `Shared_data()` in `GUI_napari.py`'s `main()`) that pre-imports the package tree and (best-effort, since it's the only node opted in today) `diplib`, then idles waiting to be handed a real node's `analysisInfo` — shortcutting the first-ever subprocess-node start in a session. **The pool, not the claiming caller, creates the worker's channels** (frame in/out queues, stop event, control pair): a `multiprocessing` Queue/Event can only cross a process boundary by *inheritance*, so they are built in `start()` and passed as `Process` args, and `try_claim()` returns them as a `channels` dict for `AnalysisProcess_customFunction.__init__` to adopt. Sending them through `assign_queue` instead raises `RuntimeError: Queue objects should only be shared between processes through inheritance` on the parent's queue-feeder *thread* — the parent continues unaware while the child blocks forever on `assign_queue.get()`, so the node silently never processes a frame (that was the shipped bug; the cold-spawn path was unaffected, which is why only pool-claimed starts broke). `assign_queue` now carries only `(analysisInfo, log_level)`. Tests: `tests/test_subprocess_pool.py`. Extend its pre-imported-library list (or generalize via an optional `"__prewarm_imports__"` metadata key) if more nodes opt into `__runInSubprocess__`.
- `shared_data._rt_subprocess_cache` (a dict keyed by `AnalysisClass._rt_config_key(analysisInfo)`, a stable hash of the node's config) lets `stop()`/`destroy()` park a still-alive, already-warmed-up worker (+ its visualisation shadow object) instead of killing it — `_park_subprocess_worker` handles the cap/idle-timeout eviction opportunistically on each park, no dedicated QTimer needed. A later `__init__` with the identical config reclaims it directly (`_worker_warmed_up = True` immediately, no spawn/import/model-load). Trade-off: a node's Python-level state (e.g. a counter set on `self` in `run()`) now survives a stop→restart of the same config instead of getting a fresh instance — undocumented per-node reset behavior would need a reset hook if this ever matters (see the class docstring's "v1 limitations"). `AnalysisClass.terminate_all_rt_subprocesses()` is wired into `GUI_napari.py`'s `aboutToQuit` (before the forced `os._exit(0)`) so parked/warm processes don't get orphaned.

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
