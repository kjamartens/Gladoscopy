# claude_issues.md — issue inbox

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

## Open issues

*(none — all resolved or scheduled)*

---

## Scheduled / deferred (will be addressed by a specific plan phase)

- **pymmcore-plus MDA zarr storage** — crashes fixed (MDA_acq_finished and pyMMCdataset.finish() no longer crash); actual zarr storage for pymmcore-plus MDA + advanced-settings storage selector deferred to a future plan step.
- **MDA black slices** — deferred by user until Phase 13 is fully complete; ask again then. Fast MDA (50 frames at 20 ms) leaves black slices in the napari stack because not all frames arrive in time.
- **Napari layer thumbnail loading icon** — user suggested ignoring. The icon spins on every `layer.data =` assignment; suppressing it requires internal napari APIs. Defer unless user flags as priority.
- **RT counter / FFT fps drops to ~2 fps** — user deferred until Phase 13 is fully done.

---

## Resolved (history)

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
