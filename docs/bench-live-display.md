# Live video feed throughput — benchmark methodology and results

Standalone deep-dive into raw display throughput for the live video feed,
independent of `claude_project.md` Phase 13 (which already covers the same
pipeline but was driven entirely by one-off `cProfile` dumps from a full
end-to-end app run, with no repeatable, hardware-free way to A/B test
competing fixes). This doc covers the harness built for that, the six
candidates it was used to test, what was actually implemented, plus a
follow-up (candidate 7) that landed the "reduce `useq.MDAEvent` Pydantic
validations per frame" item from `docs/perf-runtime-recipe.md`'s "Next perf
passes" list.

See also: `docs/napari-vis-strategy.md` (Phase 13.5's pipeline/bottleneck
writeup), `docs/perf-runtime-recipe.md` (the existing end-to-end `cProfile`
harness this work complements).

## Methodology

`scripts/bench_live_display.py` calls the real production functions
(`napariGlados.napariUpdateLive` / `_napariUpdateLive_locked`) directly —
not a reimplementation — by setting the module-level `shared_data` global
the same way `runNapariPycroManager` does, and feeding synthetic frames
through a minimal fake `shared_data`/`MILcore` (following the
`tests/fakes/fake_mil.py` pattern) instead of a real Micro-Manager backend.
It drives a real `napari.Viewer()` — napari's own rendering cost is exactly
what's being measured, so that part isn't mocked.

Run it with `make bench-live-display` (or
`python -m scripts.bench_live_display --mode layer-update`). Results append
to `docs/bench-live-display.txt`, timestamped, same convention as
`docs/perf-runtime.txt`.

Two modes:
- `layer-update` — steady-state ms/frame for the actual display-update
  code path, at 512², 1024², and 2048² uint16, with toggles for each
  candidate below.
- `queue-depth` — an analytical (non-threaded) simulation of the
  visualisation queue's frame-drop behavior at different `maxlen`, driven
  by a real measured render cost.

`scripts/bench_pyqtgraph_vs_napari.py` is a separate, narrower spike
comparing napari's Image layer against a bare pyqtgraph `ImageItem` (kept
for reproducibility even though the result was negative — see candidate 6).

**Environment note:** this work was done in a sandboxed dev environment
without a working PYCROMANAGER_JAVA bridge or a stable pymmcore-plus+Qt
process (see "What could not be verified end-to-end" below). The exposure
Java-bridge round trip is therefore *modeled* (`--java-latency-ms`), not
measured live; everything else (contrast, logging, layer scan, pyqtgraph)
is a real, unmodeled measurement.

## Candidates tested

| # | Candidate | Result | Verdict |
|---|---|---|---|
| 1 | Cache `MILcore.get_exposure()` | ~280ms → ~15-20ms/frame at a modeled 257ms Java round-trip (matches the pre-cache `get_pixel_size_um` cost) | **Implemented** |
| 2 | Cache `getLayerIdFromName` lookup | The lookup itself measured ~47µs even with 51 layers present — negligible, not a bottleneck | **Rejected** (see finding below) |
| 3 | Guard hot-path `logging.debug`/`.info` f-strings behind `isEnabledFor` | Modest, real: ~1-2ms/frame at 512-1024px between WARNING and DEBUG on the *unguarded* code | **Implemented** |
| 4 | Contrast strategy: auto (every frame) vs. fixed vs. throttled | Auto 20.7ms vs. fixed 15.25ms vs. throttled-every-10 15.3ms @ 2048² — throttled gets ~all of the fixed-contrast win while still adapting brightness | **Implemented** (throttled) |
| 5 | Visualisation queue depth (`maxlen` 1 vs. 2 vs. 3) | Simulated at render-bound rates (render slower than arrival): identical rendered/dropped counts regardless of `maxlen` — a deeper queue only adds latency, not throughput, when the UI thread is the bottleneck | **Rejected**, no change |
| 6 | Bare pyqtgraph `ImageItem` vs. napari `Image` layer | napari (fixed contrast) 16.1ms vs. bare pyqtgraph `ImageItem` 38.8ms @ 2048² — napari wins by >2x | **Rejected**, keep napari |
| 7 | Lazy-convert `useq.MDASequence` → pycromanager events for `_mdaModeParams` instead of eagerly at live-mode batch start | Eager `to_pycromanager()` on a 999-event live-mode sequence measured ~60ms, entirely duplicated work since `run_mda()` re-iterates+re-validates the same sequence internally to drive acquisition | **Implemented** |

### 1 — Exposure caching (implemented)

`napariUpdateLive`'s rate-limit gate calls `shared_data.MILcore.get_exposure()`
on every candidate displayed frame (`napariGlados.py:102`, before the frame
even reaches the display-update logic). For `PYCROMANAGER_JAVA` this is an
uncached Java-bridge round trip — unlike `get_pixel_size_um()`, which
already got a cache in Phase 13.2 after being profiled at ~257ms/call.

No real Java bridge was available to measure this live in this environment,
so the round-trip cost was modeled with `--java-latency-ms 257` (matching
the pixel-size profile) wrapping a `FakeMicroscopeInterfaceLayer.get_exposure`
call. Cached vs. uncached at that modeled latency:

```
uncached:  steady_mean ≈ 278-286ms/frame (all three frame sizes)
cached:    steady_mean ≈ 13-20ms/frame   (all three frame sizes)
```

Implemented in `MicroscopeInterfaceLayer.get_exposure()`
(`glados_pycromanager/Core/microscopeInterfaceLayer.py`), mirroring the
exact `get_pixel_size_um` cache pattern: cached after first call,
invalidated by `set_exposure()` and by `set_core()`. Only matters in
practice for `PYCROMANAGER_JAVA`; `MMCORE_PLUS`/`PYCROMANAGER_PYTHON` calls
are already in-process and cheap.

### 2 — Layer lookup (rejected; real finding was elsewhere)

The original hypothesis (an `O(n)` Python-level scan in
`getLayerIdFromName`) turned out to be a red herring: a direct microbenchmark
of the function alone, with 51 layers present in the viewer, measured
~47 microseconds per call — utterly negligible next to a frame budget
measured in milliseconds.

However, pre-populating the viewer with 50 dummy layers before running the
full `layer-update` benchmark showed steady-state cost jump from ~13-20ms
to **~70-75ms/frame** — a 4-5x regression. Isolating `layer.refresh()`
(~2ms) and `app.processEvents()` (~4ms) individually with the same 51
layers present did *not* reproduce that cost in isolation; only the
combination (mutate + refresh + processEvents, repeated) did. This points
at napari/Qt's redraw machinery (likely the layer-list side panel or canvas
occlusion/visibility bookkeeping) doing work that scales with *total* layer
count, not at the name-lookup scan specifically.

**This is a real finding, not fixed in this pass** — the root cause sits
inside napari-internals territory (consistent with
`docs/perf-runtime-recipe.md`'s existing "Next perf passes" note that
deeper napari internals are out of easy reach). Flagged here for whoever
picks up the next perf pass, especially since this app's RT-analysis dock
is designed to accumulate many layers in a single session.

### 3 — Hot-path logging guards (implemented)

Several `logging.debug(f"...")`/`logging.info(f"...")` calls in the
per-frame path build their f-string unconditionally before the logger
decides the configured level allows it through — Python's `logging` module
does not lazily format f-string arguments. Comparing DEBUG vs. WARNING
level on the *unguarded* code showed a real, if modest, tax:

```
512px:  DEBUG 13.97ms vs WARNING 11.61ms
1024px: DEBUG 14.94ms vs WARNING 13.56ms
2048px: DEBUG 21.29ms vs WARNING 20.34ms
```

Guarded every hot-path call (`napariUpdateLive`'s rate-limit gate,
`put_data_in_visualisation_and_analysis_queues`,
`grab_image_liveVisualisation_and_liveAnalysis`,
`grab_image_liveVisualisation_and_liveAnalysis_savedFn`, and the per-frame
`multiDstack` dimension/slice-lookup logging) behind
`logging.getLogger(__name__).isEnabledFor(...)`, mirroring the existing
`Shared_data.__setattr__` fix from Phase 13.8.

### 4 — Contrast strategy (implemented: throttled)

`layer._keep_auto_contrast = True` makes napari recompute contrast limits
(a full min/max scan) on every single frame update. This measured as the
single largest recurring per-frame cost in the whole path:

```
                 512px    1024px   2048px
auto (every frame)  13.8ms   14.6ms   20.7ms
fixed (never)        9.8ms   11.1ms   15.3ms
throttled (every 10) —        —       15.3ms  (measured @ 2048px)
```

A permanently fixed contrast loses real UX value (the preview stops
adapting to scene brightness changes), so the implemented fix instead
recomputes on a throttle: every N displayed frames (default 10, new
`visualisation_config.contrast_refresh_every_n_frames` setting), landing
within measurement noise of the fully-fixed cost while still tracking
brightness roughly every 166ms at default FPS/N. A full setter reassignment
(shape/dtype change mid-session, e.g. ROI/binning change) forces an
immediate recompute rather than waiting for the throttle, so a genuine
frame-shape change never displays with stale limits.

Implemented in `glados_pycromanager/GUI/napariGlados.py`
(`_maybe_refresh_contrast`, `_get_contrast_frame_counters`) and
`glados_pycromanager/GUI/sharedFunctions.py` (`VisualisationConfig.contrast_refresh_every_n_frames`).

### 5 — Visualisation queue depth (rejected)

Simulated (analytically, not threaded) via `--mode queue-depth`: given a
render cost and a camera arrival interval, when the renderer is the
bottleneck (arrival faster than render, the common case for a fast camera
against a UI-thread-bound display), `maxlen` 1 vs. 2 vs. 3 produced
*identical* rendered/dropped counts in every configuration tested — a
deeper queue only changes which frames get shown (adds latency to the
displayed frame), it doesn't increase total throughput. This confirms the
qualitative reasoning already in `docs/napari-vis-strategy.md` B2. No
change made.

### 6 — pyqtgraph vs. napari (rejected)

Spiked whether napari's `Image` layer (event system, thumbnail, contrast
pipeline) is inherently the wrong tool for a bare live preview, given
`pyqtgraph` is already a pinned dependency (used for laser-control plots).
Side-by-side at 2048², both with a fixed contrast/no extra chrome:

```
napari Image layer (fixed contrast):   16.1 ms/frame
bare pyqtgraph ImageItem (no chrome):  38.8 ms/frame
```

napari wins by more than 2x even in its leanest configuration against
pyqtgraph's leanest configuration (`GraphicsLayoutWidget` + bare
`ImageItem`, no histogram/ROI chrome). **No architecture change pursued.**

**Windows gotcha found during this spike:** importing `pyqtgraph` before
`PyQt5.QtWidgets.QApplication` crashes the process immediately with no
traceback on this environment — the same class of Qt-binding-order issue
already documented in `docs/perf-runtime-recipe.md` for napari vs.
pymmcore-plus. `scripts/bench_pyqtgraph_vs_napari.py` imports `QApplication`
first for this reason; keep that order if this script is ever extended.

### 7 — Lazy MDASequence → pycromanager conversion (implemented)

Direct follow-up on `docs/perf-runtime-recipe.md`'s "Next perf passes"
item 1 ("reducing the number of `useq.MDAEvent` Pydantic validations per
frame"), found by reading the actual live-mode MMCORE_PLUS code path
(`napariGlados.py:run_MILCoreAcquisition_worker`) rather than benchmarking:

```python
mda_sequence_useq = useq.MDASequence(time_plan={"interval": 0.0, "loops": live_mode_nr_frames})
shared_data._mdaModeParams = to_pycromanager(mda_sequence_useq)  # (was) eager, full iteration
self.shared_data.MILcore.core.run_mda(mda_sequence_useq)          # iterates+validates again, internally
```

`to_pycromanager(sequence)` for a `MDASequence` eagerly does
`[_event_to_pycromanager(event) for event in obj]` — a full iteration that
pydantic-validates every `MDAEvent` in the sequence immediately (999 events
for the default `live_mode_nr_frames`). `core.run_mda()` then iterates the
*same* sequence again, lazily, internally, to actually drive acquisition —
so every live-mode batch restart paid for validating each event twice.
Measured directly:

```
to_pycromanager(999-event sequence): 59.70ms, 999 events validated
list(sequence) (bare useq iteration): 64.95ms, 999 events
```

i.e. the eager conversion cost ~60ms per batch restart, entirely
duplicated. `shared_data._mdaModeParams` is only read by
`_get_cached_dimensions` (never called for the plain `layer_name == 'Live'`
display path) and by RT-analysis dimension bookkeeping in
`pSMLM.py`/`RT_counter.py` (only when such a node is actually running) — so
the eager conversion was pure waste in the common plain-live-preview case.

Made `Shared_data._mdaModeParams` a property: live mode now assigns the raw
`useq.MDASequence` directly; the property's getter converts (and caches)
only on first actual read. MDA mode's existing assignment (an
already-converted pycromanager event list) passes straight through the
getter unchanged. Implemented in
`glados_pycromanager/GUI/sharedFunctions.py`
(`Shared_data._mdaModeParams` property) and
`glados_pycromanager/GUI/napariGlados.py` (live-mode assignment site).
Locked in by `tests/test_shared_data_mda_params_lazy.py`.

## What could not be verified end-to-end

`make profile-runtime` (the existing full-app `cProfile` harness against
the pymmcore-plus demo camera) segfaults immediately in this sandboxed dev
environment, right after CMMCorePlus/demo-camera startup and before any
frame-display code runs. This was confirmed to be **pre-existing and
unrelated to this work**: checking out the commit immediately before these
changes (`684dbbb`) reproduces the identical crash. It's consistent with
the Qt/pymmcore-plus DLL-ordering fragility already documented in
`docs/perf-runtime-recipe.md`, just triggering earlier/differently than in
whatever environment produced the existing `docs/perf-runtime.txt` entries.

All four implemented changes were instead validated by:
- The `bench_live_display` micro-benchmark, which exercises the real
  production functions directly (not a reimplementation).
- The full `pytest -q` suite (308 passed, no regressions).
- New unit tests for the exposure cache
  (`tests/test_mil_dispatch.py::test_get_exposure_caches_after_first_call`
  and siblings), mirroring the existing pixel-size cache test coverage, and
  for the lazy MDASequence conversion
  (`tests/test_shared_data_mda_params_lazy.py`).

**Recommended follow-up for whoever has a working interactive session**:
run `make profile-runtime PROFILE_SECS=15` before/after this branch and
diff against `docs/perf-runtime.txt`, per the existing checklist in
`docs/perf-runtime-recipe.md`. Also worth a manual smoke check: start/stop
live mode a few times, confirm the image displays correctly (contrast,
colormap, layer creation) in both `frameByFrame` and `multiDstack` modes
with a real backend — this was not possible to do visually in this
environment.
