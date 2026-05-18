# Runtime performance recipe — Phase 13.7

How to run a live-mode profile, interpret the output, and what to do next.

---

## 1. Prerequisites

```
conda activate GladosEnv        # or: source .venv/Scripts/activate
make dev                        # editable install with dev extras
```

No hardware is required — the pymmcore-plus bundled demo camera is used.

---

## 2. Running a profile

### Quickest path

```
make profile-runtime
```

Default sample window is 8 s (`PROFILE_SECS=8`).  To change it:

```
make profile-runtime PROFILE_SECS=15
```

Equivalent manual command (for IDE / debugger):

```
python -m glados_pycromanager.GUI.GUI_napari \
    --auto-demo \
    --profile-runtime 8
```

### What happens

1. `--auto-demo` bypasses the headless-backend popup by selecting
   PyMMCorePlus + bundled demo camera automatically.
2. `--profile-runtime N` wraps the entire `runNapariPycroManager` call in
   `cProfile.Profile()`.
3. A `QTimer` fires every 500 ms to check whether `liveMode` is still True.
4. The profile is dumped (top-25 by cumtime) to `docs/perf-runtime.txt` and
   to the console on whichever comes first:
   - The N-second timer fires.
   - Live mode self-terminates (the demo cam auto-stops after 999 frames).
   - The napari window closes (`aboutToQuit`).

The file is **appended**, not overwritten, so you keep a history of runs.

---

## 3. Interpreting `docs/perf-runtime.txt`

Each section header shows the timestamp, the sample duration, and how many
`napariUpdateLive` calls were observed (= how many frames reached the UI
thread for rendering).

The `ncalls / tottime / cumtime` columns are standard cProfile output.
Key columns to focus on:

| Column | What it means |
|--------|---------------|
| `ncalls` | How many times the function was called in the window |
| `tottime` | Time spent *inside* the function (excludes callees) |
| `cumtime` | Time spent inside + all callees — use this to find bottlenecks |
| `percall` (second) | `cumtime / ncalls` — cost per invocation |

### What to look for

- **High `cumtime` + few `ncalls`** → a slow per-call operation (e.g.
  `napari.add_image` at 1.284 s in run 2 is called once and is expensive).
- **High `cumtime` + many `ncalls`** → a hot loop path (e.g. `processEvents`
  called 717 times in run 1 = 12.568 s total; that's the UI-thread hazard
  fixed in Phase 13.2).
- **`time.sleep` in the top-25** → something is sleeping on the critical path;
  investigate which call site.
- **`get_pixel_size_um`** → was 1.285 s cumulative across 5 calls in run 2
  (Java bridge round-trip); fixed by pixel-size cache in Phase 13.2.

---

## 4. Known gotchas

### Qt import ordering vs pymmcore-plus

On Windows, importing `PyQt5` (or `PySide2`) after `pymmcore_plus.CMMCorePlus`
causes a DLL ordering conflict that manifests as a `STATUS_STACK_BUFFER_OVERRUN`
crash on process exit.  The fix — already in place — is to set:

```python
os.environ["NAPARI_ASYNC"] = "1"
os.environ["NAPARI_OCTREE"] = "1"
```

**before** any `import napari` and to let napari's own Qt import happen first.
Never import `CMMCorePlus` at the top level; import it inside the function that
needs it so that napari's Qt import has already resolved.

### Why in-process cProfile, not a wrapper script

The straightforward approach (wrap the launch with `python -m cProfile`) does
not work here because:

1. `cProfile` started before napari's event loop cannot cleanly dump after
   `app.exec_()` returns — the `os._exit(0)` handler (added in Phase 12)
   exits the process without returning from `exec_()`.
2. A `cProfile.run("main()")` wrapper also misses cleanup.

The `--profile-runtime` flag runs the profiler **inside** the process via
`cProfile.Profile()`, dumps explicitly to file, and lets `os._exit(0)` handle
the final teardown.

### The demo cam completes early

The pymmcore-plus demo camera auto-stops after 999 frames (the default
`live_mode_nr_frames`).  If your sample window is longer than the time it
takes to capture 999 frames, the watchdog will dump the profile early (the
`liveMode-auto-stop` trigger).  Check the header line:
`N napariUpdateLive calls observed` — a low number here means the demo
completed before your window elapsed.  This is normal; the profile data is
still valid.

### Profile overhead

cProfile adds ~5–10 % overhead to every Python function call.  The absolute
timings in `perf-runtime.txt` are slightly inflated compared to uninstrumented
production runs; the *relative* ratios between functions are still accurate and
the bottleneck ranking is reliable.

---

## 5. Phase 13 optimization checklist (reference)

Use this when reviewing future perf profiles:

- [ ] `processEvents` not in top-25 (was fixed Phase 13.2)
- [ ] `get_pixel_size_um` total cumtime < 0.05 s per session (pixel-size
      cache, Phase 13.2)
- [ ] No `time.sleep` in `napariUpdateLive` call chain (fixed Phase 13.3)
- [ ] `np.ascontiguousarray` present in `napariUpdateLive` call chain
      (Phase 13.6)
- [ ] `zarr.open` called once per MDA sequence, not per frame
- [ ] `napari.add_image` called once per layer per session (first frame only);
      subsequent frames use `layer.data[:] =` (Phase 13.6)
- [ ] No `napariViewer.reset_view()` called after first frame (expensive
      camera frustum recalculation)

### Targets (demo cam, MMCORE_PLUS backend, 2 k × 2 k sensor)

| Metric | Before Phase 13 | After Phase 13 |
|--------|----------------|----------------|
| Frames in 8 s | 433 (run 1) | TBD (next profile run) |
| processEvents cumtime | 12.568 s | 0 s (disabled) |
| get_pixel_size_um cumtime | 1.285 s | < 0.05 s (cached) |
| time.sleep in napariUpdateLive | present | removed |

---

## 6. Next perf passes (Phase 14+)

After Phase 13 the remaining hot paths in the profile are inside pymmcore-plus
and napari's own internals (`_iter_exec_output`, `exec_sequenced_event`,
`pydantic` model validation per event).  These are not addressable without
patches to upstream dependencies.  The next productive perf pass should focus
on:

1. Reducing the number of `useq.MDAEvent` Pydantic validations per frame
   (currently ~3–4 validation calls per frame visible in the profile).
2. Profiling with a real hardware camera (demo cam uses a software sleep per
   frame that dominates the `time.sleep` tottime).
3. Evaluating whether `NAPARI_ASYNC=1` + `NAPARI_OCTREE=1` help with tiled
   large-sensor images (> 4 k × 4 k).
