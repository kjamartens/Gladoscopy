# claude_issues_and_features.md — issue/features inbox

This file is the inbox for bugs, regressions, or follow-ups that must be
fixed **before** further progress on `claude_project.md`.

When the user says **"continue"**, Claude reads this file first and resolves
every unchecked item in **Open issues** in its own commit on the
`claude_optimization` branch, marking the item `- [x]` as it is fixed. Only
when the open list is empty does Claude advance to the next un-committed
step in `claude_project.md`.

Issues that already have a documented home in a future plan phase live
under **Scheduled / deferred** — they are reminders, not blockers. Moving
an item into that section requires either (a) the issue itself naming a
phase, or (b) a fresh decision entry in `claude_decisions.md` explaining
why the deferral is safe.

## How to add an issue

Append a checklist item under `## Open issues`:

```
- [ ] short description (file:line if relevant) — reproduction / context
```

Add longer context underneath as a nested bullet if needed.

---

## Open issues/features
[] RT methods ideally have their visualisation processed on a different core - right now, while visualisation is prepared, the visualisation (or something else, but looks as visualision) of the live view is hindered/hiccups.
[] Investigate whether the following is possible, and if so, implement as a new RT script: I want to do the pSMLM analysis on the fly, and show the localized spots on top of the image, as well as show a SR image next to it. Now I see a few issues. 1: there should be 2 layers created as far as i know, not sure if the plumbing can be updated to allow this. 2: ideally i want to show the pSMLM localization a little delayed compared to the raw data - i.e. lets say pSMLM analysis takes 2 ms, and i get a frame every 50 ms, I believe with my current updating, my pSMLM is always 1 frame behind. I would be perfectly happy to just have pSMLM-visualise show the 'old' frame with the overlaid localizations - but then it needs to create 3 layers I believe. Issue 3: With toggle grid-mode, i can have layers on top of each other, or side-by-side, but here i want a mix: i want live/pSMLM-'old'/pSMLM-'locs' overlaid, and then the pSMLM-SR to the side. If this is not possible with grid-mode, are there other options?
[] Can we support RT analysis which has this stored in memory when a MDA is done, and then re-show it during scrubbing of the movie? I.e. with pSMLM-version, where it just shows circles now, i want to have a MDA and scrub through the movie, and show me what it analysed in those frames. Ideally, I want the scripts used for RT analyses to remain the same (or similar), and have all of this in glados back-end.

[] **Flaky (rarely) under a full-suite run: `tests/test_perf_capture_subprocess_ipc.py::test_profiling_start_stop_round_trip_does_not_disturb_frames`** — failed once in a full `pytest -q` run on 2026-09-09, passed in isolation and on the immediately following full run. Its `out_queue.get(timeout=10)` calls have to cover a cold `spawn` that re-imports the whole package tree; under load from the other spawn-based tests that can exceed 10 s. Not a product bug. Fix by giving the first `get()` a longer, cold-start-sized timeout (the same distinction `AnalysisProcess_customFunction` already makes between its 30 s cold and 5 s warm timeouts), or by polling `proc.is_alive()` like `_get_or_fail_fast` in `test_analysis_process.py`.


---

## Scheduled / deferred (will be addressed by a specific plan phase)

- **Per-frame display cost grows ~0.5 ms per napari layer that exists** (T-E5
  measurement, `docs/bench-live-display.md` "Re-measured after T-E1 - T-E4").
  Steady-state frame cost is roughly `15.6 + 0.5 x N` ms with N layers in the
  viewer: 15.6 ms at 0, 40.3 ms at 50. It is independent of frame size, so it is
  per-layer bookkeeping inside napari/Qt, not pixel work. This matters here
  because the RT-analysis dock is *designed* to accumulate overlay layers over a
  session.
  - **Hiding does not work.** `visible = False` on all 50 layers measured within
    noise of leaving them visible (39.8 vs 40.3 ms), so the cost scales with
    layers that *exist*, not layers being rendered. The cheap mitigation is off
    the table; measured with `bench_live_display --hide-existing-layers`.
  - **Remaining options**, both requiring layer-lifecycle work rather than a
    display-path change: (a) have each RT-analysis node reuse one overlay layer
    across runs instead of adding a new one, and (b) cap the number of
    accumulated overlay layers with oldest-first eviction.
  - Deferred deliberately: T-E5 is a measurement task and says not to attempt a
    fix. See `claude_decisions.md` (2026-09-09, T-E5) for why this is safe to
    defer.

- **Napari layer thumbnail loading icon** — user suggested ignoring. The icon spins on every `layer.data =` assignment; suppressing it requires internal napari APIs. Defer unless user flags as priority.


---

## Resolved (history)

- [x] **Read-only configuration groups** — `ConfigInfo.isReadOnly()` derives it purely at
  render time (no new persisted flag: MMCore's `.cfg` format has no such concept) from
  `MIL.is_property_read_only()` over the group's property set (reusing
  `config_group_editor.group_property_set()`); a group is read-only iff every device
  property backing it is. `addLabel()` checks it before dropdown/slider/input-field and
  renders a plain `QLabel` instead, refreshed the same way the other widget types are.
  Matches the `Real_ms`-style status group in `DemoSMLM.cfg`. Tests:
  `tests/test_mmconfig_panel.py`.
- [x] **Live-view contrast mode driven by napari's native auto-contrast toggle** —
  Glados no longer forces its own throttle regardless of user choice. New live/MDA/album
  layers now seed `_keep_auto_contrast = True` at creation (napari's own "continuous"),
  the same flag napari's built-in auto-contrast button reads/writes; switching to "once"
  or dragging the contrast sliders manually now actually holds the range, since
  `_maybe_refresh_contrast` does nothing at all while the flag is `False`. multiDstack no
  longer needs a separate Glados-side call (napari's own slicing pipeline already
  recomputes natively via `dims.set_current_step`); frameByFrame keeps the throttled
  call since its in-place data update bypasses that pipeline. Tests:
  `tests/test_contrast_throttle.py`.
- [x] **Exposure change restarts live mode** — editing the exposure-time field while
  live mode is running used to have no effect until the next live-mode start.
  `_onExposureFieldEditingFinished()` now checks `shared_data.liveMode` and, if running,
  spawns `_exposureChange_liveRestart` on a daemon thread mirroring `setROI`'s live
  restart (stop, wait, `set_exposure`, wait, restart). Tests:
  `tests/test_mode_setter_no_sleep.py`.
- [x] **pymmcore-plus MDA saved nothing / ignored the user's Storage folder** — the two
  deferred items above, fixed together. `run_mda()` was called with no `output=`, so the
  only copy of the frames was the scratch display zarr in a `TemporaryDirectory` that
  `release_all_temp_dirs()` deletes on exit; `savefolder`/`savename` were computed and
  never read. This backend has no NDTiff engine, so pymmcore-plus now does the recording
  itself: `mmcore_output_path()` builds `<Storage folder>/<name>.ome.zarr` (or `.ome.tiff`)
  from the new `MDAConfig.mmcore_save_format` dropdown, never overwriting an existing
  acquisition, and `run_mda(output=...)` writes it. The runner thread is joined so the
  handler finalises before the storage path is reported, and
  `_acquisition_storage_path()` now prefers `shared_data.mdaSavedPath` over the scratch
  store's temp directory. Verified end-to-end against pymmcore-plus' bundled demo camera
  (`tests/test_mmcore_mda_saving.py`), including reading the data back at the
  acquisition's shape. Committed in `fix(storage): save pymmcore-plus MDAs to the user's Storage folder`.

- [x] **Live/MDA mode on MMCORE_PLUS ran but showed no image (regression from Phase 13.2)** — `core.mda.events` is a Qt-backed (PyQt5) signaler whenever a `QApplication` is running (always true in this GUI app); `frameReady`/`sequenceStarted`/`sequenceFinished`/`sequenceCanceled` were connected inside `run_MILCoreAcquisition_worker`, a napari `@thread_worker` QThreadPool worker thread with no Qt event loop of its own. Under default `Qt.AutoConnection` the callback invocation queued for that thread and was never dispatched — Phase 13.2's removed `processEvents()` polling turned out to be the only thing draining that queue, not dead overhead as assumed. Fixed by connecting with an explicit `Qt.DirectConnection` via a new `_connect_mda_signal_direct()` helper (faster than the original pre-13.2 code, since it needs no polling at all). Also fixed an unrelated real bug found during triage: `napariUpdateLive`'s `liveModeUpdateOngoing` reentrancy guard could get stuck `True` forever on an early return, permanently freezing the live layer for the rest of the session — now wrapped in `try/finally`. See `claude_decisions.md` (2026-07-15) for full root-cause detail. Committed in `fix: deliver MMCORE_PLUS MDA signals via Qt.DirectConnection`.
- [x] **`liveMode` flips back to False ~1 s after being set programmatically** — Three improvements committed: (1) traceback diagnostic in the `liveMode` setter logs the full call stack on every False transition (DEBUG level) — re-run `make profile-runtime PROFILE_SECS=8` to capture the stack; (2) `stop_sequence_acquisition()` for MMCORE_PLUS now also calls `core.mda.cancel()` when an MDA is running — `stopSequenceAcquisition()` alone does not cancel a `run_mda`-based sequence; (3) profiler watchdog delay increased from 500 ms → 1500 ms and `mdaMode` guard added to `_profile_try_start` to avoid false-positive early dumps when the demo cam completes its first 999-frame batch and the worker momentarily re-arms. Committed in `reliability: diagnose liveMode flip + fix MMCORE_PLUS stop + robustify profiler watchdog`.
- [x] **`make run-dev` / `make run-prod`** — added `run-dev` (editable dev install then launch) and `run-prod` (non-editable production install then launch) combined targets to `Makefile`. Updated `.PHONY` list and top-of-file quick-start comment. Committed in `build: add run-dev and run-prod combined targets`.
- [x] **`MIL.create_mda` mutable-default trap** — fixed in Phase 10.8. Mutable defaults replaced with `None`; bare `create_mda(num_time_points=N)` now yields a clean time-only event list. Bad plans (negative frames, zero-step z-stack, empty channel name, exposure/channel mismatch, channels without channel_group) raise `MDAEventError`. The regression test `test_default_call_raises_due_to_mutex_defaults` was renamed and inverted to `test_default_call_now_produces_time_only_events` and now asserts the saner default behaviour.
- [x] **pyjavaz bridge thread traceback on startup** — replaced the blind `Core()` try/except with a 200 ms `socket.create_connection` probe on port 4827. If nothing is listening, the headless dialog opens immediately with no bridge thread spawned and no traceback. Committed in `fix: suppress pyjavaz bridge noise via pre-probe socket check`.
- [x] **`visualisation_worker` AttributeError on first autonomous-microscopy run** — `napariHandler.__init__` now initialises `self.visualisation_worker = None`; also fixed a double-attribute typo in `_on_worker_fully_stopped_mda`. Committed in `fix: init visualisation_worker=None`.
- [x] **Advanced settings window `TypeError: setToolTip` with QWidget** — two incorrect `label.setToolTip(editField)` calls (passing a widget instead of a string) removed from `openAdvancedSettings` in `utils.py`. Committed in `fix: remove invalid label.setToolTip(widget) calls`.
- [x] **User manual napari command missing** — added `UserManualWidget` class to `GUI_napari.py` and aliased it as `show_UserManualNapari`; fixes the "module has no attribute" error on plugin load. Committed in `fix: add show_UserManualNapari widget`.
- [x] **Developer menu `No module named 'markdown_captions'`** — `markdown_view.py` now tries to import `markdown_captions` and silently skips it if absent; `markdown-captions>=2.1` added to `pyproject.toml`. Committed in `fix: add show_UserManualNapari widget + make markdown-captions optional dep`.
- [x] **XY/Z position display stale after move** — `moveXYStage` and `moveOneDStage` now fire a `QTimer.singleShot(500 ms)` to schedule a second position read-back after the stage has had time to settle. Committed in `ux: delayed position read-back after XY/Z stage moves`.
- [x] **After-close hang (10-20 s, then Error -1073741819)** — connected `os._exit(0)` to `app.aboutToQuit` so the process force-exits when the napari window closes, bypassing Python/C destructors that hang and then segfault. Committed in `fix: force-exit on napari close`.
- [x] **pymmcore-plus MDA crash on completion** — `MDA_acq_finished` caught `IndexError` but the zarr fallback raised `KeyError('MDA')`, crashing the handler. Now catches both, sets `self.data = None`, logs warning. `pyMMCdataset.finish()` exception level lowered to DEBUG (expected until put_image is implemented). Committed in `fix: prevent MDA_acq_finished crash`.
- [x] **Hot-swap custom nodes** — added `reload_all_node_modules()` to `discovery.py` and wired it to `Plugins > Reload Glados Custom Nodes` in the napari menu bar. Committed in `feat: hot-swap custom nodes`.
- [x] **RT counter / FFT fps drops to ~2 fps** — root cause: `AnalysisThread_customFunction_Visualisation.run()` called napari layer ops directly from a background QThread, blocking ~400 ms/frame. Fix: added `_do_visualise = pyqtSignal(object)` connected to `_visualise_on_main_thread` slot; `run()` now emits (non-blocking queued connection) instead of calling napari ops directly. Also removed duplicate code blocks and duplicate method/Event definitions in the same file. Committed in `fix: dispatch RT visualisation updates to main thread, remove dup code`.
- [x] **MDA black slices (MMCORE_PLUS fast MDA)** — root cause: vis queue only captures ~fps frames/s; MMCORE_PLUS has no NDTiff store to recover dropped frames, and the finalisation procedure threw uncaught `AttributeError` on `None._dataset`. Fix: `_try_write_frame_to_zarr` writes every frame directly to zarr from the `frameReady` callback for multiDstack mode; finalisation except now also catches `AttributeError`. Committed in `fix: prevent MDA black slices for fast MMCORE_PLUS acquisitions`.
- [x] **Reload Custom Nodes in wrong menu position** — action was in the top-level Plugins menu; now placed inside the "Glados-PycroManager" plugin sub-menu (created by napari from napari.yaml), with fallback to top-level. Committed in `ux: place Reload Custom Nodes action in Glados-PycroManager plugin sub-menu`.
