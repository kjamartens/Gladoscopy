# Napari visualization strategy — Phase 13.5

Produced 2026-05-18 as part of Phase 13.5.  Covers the current image-delivery
pipeline per MIL backend, identified bottlenecks, and a ranked list of
optimizations for Phase 13.6.

---

## 1. Pipeline overview

All three backends share the same downstream visualization chain:

```
Hardware / software camera
        │  (backend-specific callback, worker thread)
        ▼
  grab_image_*()          napariGlados.py:402 / 425 / 474
        │  put_data_in_visualisation_and_analysis_queues()
        ▼
  visualisation_queue     deque(maxlen=10); single-slot insert ("< 1")
        │  (sets _new_image Event)
        ▼
  run_napariVisualisation_worker   @thread_worker (QThread)
        │  .wait(_new_image); yield DataStructure
        ▼
  napariUpdateLive()       napariGlados.py:46   ← RUNS ON UI THREAD
        │
        ▼
  napari layer update     layer.data = img  or  zarr_store[slice] = img
```

### 1.1 MMCORE_PLUS backend

`run_MILCoreAcquisition_worker` calls `core.run_mda(mda_sequence_useq)` in
a `@thread_worker`.  Images arrive via `core.mda.events.frameReady.connect(
grab_image_liveVis_PyMMCore)`.  The callback receives a `np.ndarray` directly
— no disk read needed.  After the MDA, the worker spins on
`core.mda.is_running()` with `time.sleep(0.01)`.

### 1.2 PYCROMANAGER_JAVA / PYCROMANAGER_PYTHON "saved" backend

`Acquisition(image_saved_fn=grab_image_liveVisualisation_and_liveAnalysis_savedFn)`.
The callback is called by pycromanager in its own thread when a frame is
written to the NDTiff store.  It calls `dataset.read_image(**axes)` — a disk
read per frame — before putting the numpy array into the queue.

### 1.3 PYCROMANAGER_PYTHON "headless" backend

`Acquisition(image_process_fn=grab_image_liveVisualisation_and_liveAnalysis)`.
The image numpy array is passed in-memory; no disk read.  Same downstream
path.

---

## 2. Identified bottlenecks

### B1 — disk read per frame (saved backend only)

`grab_image_liveVisualisation_and_liveAnalysis_savedFn` calls
`dataset.read_image(**axes)` on every frame.  This is a synchronous disk read
in the pycromanager callback thread.  It is only present on the "saved"
backend; MMCORE_PLUS and "headless/Python" pass the array directly.

**Severity:** medium (adds ~1–5 ms per frame at SSD speeds; on spinning disk
could be 10–50 ms).  Only affects one backend path.

### B2 — single-slot visualisation queue

`put_data_in_visualisation_and_analysis_queues` only appends if
`len(visualisation_queue) < 1`.  This means at most 1 frame is ever waiting
in the queue; every subsequent frame that arrives while the UI thread is
rendering the previous one is silently dropped.

**Severity:** medium.  On its own this is actually intentional (keep latency
low, avoid queuing up stale frames).  But if the UI thread finishes rendering
just before the next camera frame arrives, we get a brief idle gap.  A maxlen
of 2 would allow one "prefetch" frame without significant latency increase.

### B3 — no contiguous C-order guarantee before `layer.data = img`

Images from hardware callbacks arrive as whatever dtype/strides the camera
driver produces.  If the array is not C-contiguous or not float32/uint16,
napari's internal path calls `np.asarray(data)` which may allocate a copy.
For large frames (2048×2048 × uint16 = 8 MB) this copy happens on the UI
thread.

**Severity:** low–medium.  MMCORE_PLUS already delivers C-contiguous uint16.
pycromanager's `read_image` also produces C-contiguous arrays.  Explicitly
enforcing it is cheap insurance.

### B4 — `rendering='attenuated_mip'` for 2D live images

`napariViewer.add_image(liveImage, rendering='attenuated_mip', ...)` is used
for the `frameByFrame` live path (line 97).  `attenuated_mip` is a 3D
volumetric renderer; for 2D data napari ignores it and falls back to its
default 2D renderer anyway, but the internal check adds a small overhead on
every `add_image` call and on first render.

**Severity:** very low.  Cosmetic correctness issue more than a bottleneck.

### B5 — zarr temp-dir ownership bug

`multiDstack` path creates the zarr store at `tempfile.TemporaryDirectory().name`
(line 186).  `tempfile.TemporaryDirectory()` creates a managed object; calling
`.name` on an immediately-discarded temporary object means the destructor runs
at GC time — possibly cleaning up the directory while zarr is still writing.
On CPython the GC is reference-counted so this is unlikely but non-deterministic
on PyPy or when GC pressure is high.

```python
# Current (fragile):
shared_data.mdaZarrData[layerName] = zarr.open(
    str(tempfile.TemporaryDirectory().name), ...)
```

**Severity:** low in practice on CPython; potential data loss on longer MDA
runs under memory pressure.

### B6 — `napariViewer.add_image` first-call cost

Profiled at 1.284 s (perf-runtime.txt run 1).  This is now partially mitigated
by the pixel-size cache (Phase 13.2), but the core `add_image` overhead (GL
texture upload, thumbnail generation, layer registration) is still significant
on first call.

**Severity:** high on first frame only; acceptable on subsequent frames.
Not further reducible without napari internals changes.

---

## 3. NAPARI_ASYNC / NAPARI_OCTREE status

`GUI_napari.py` sets:
```python
os.environ["NAPARI_ASYNC"] = "1"
os.environ["NAPARI_OCTREE"] = "1"
```
before importing napari.  As of napari 0.4.x these are experimental env-var
flags.  `NAPARI_ASYNC=1` enables asynchronous layer loading (tiles loaded in
a background thread).  `NAPARI_OCTREE=1` enables the octree-based tiled
renderer for large images.

For live 2D microscopy with small-to-medium sensor sizes these flags offer
little benefit (the image fits in one tile; async loading has no multi-tile
advantage).  They do not hurt, but their effect is near-zero for the current
use case.  No change recommended.

---

## 4. In-place update: `layer.data[:] = img` vs `layer.data = img`

For `frameByFrame` live mode, `layer.data = liveImage` replaces the entire
array reference.  napari detects the change via its `_data_view` mechanism
and triggers a refresh.

In-place update `layer.data[:] = new_img` avoids reallocating the layer's
internal data pointer and can be faster when:
- The array shapes and dtypes match exactly.
- The napari layer already has a resident GPU texture (not the case for
  software rendering on the Qt canvas).

For the current Qt-canvas-based renderer (no GPU texture), the difference is
primarily avoiding the Python object allocation of a new ndarray.  This is a
micro-optimization (~0.1 ms on a 2 k×2 k uint16 array) but is straightforward
to apply.

**Recommendation:** apply for `frameByFrame` live-mode path where the layer
already exists.  Skip for `multiDstack` path (zarr slice assignment already
writes in-place into the zarr array).

---

## 5. Ranked optimizations for Phase 13.6

| # | Optimization | Affected path | Expected gain | Risk |
|---|---|---|---|---|
| 1 | Ensure C-contiguous uint16 before `layer.data =` | all backends | avoid hidden copy on UI thread | very low |
| 2 | Fix zarr temp-dir ownership (`TemporaryDirectory` held in a variable) | multiDstack MDA | correctness fix | very low |
| 3 | In-place `layer.data[:] = img` for existing frameByFrame layer | live + MDA frameByFrame | ~0.1 ms/frame saved | low |
| 4 | Remove `rendering='attenuated_mip'` from 2D `add_image` call | live mode | cosmetic + tiny overhead | very low |
| 5 | Increase vis queue to maxlen=2 + append if `< 2` | all backends | reduce idle gaps between frames | low |

Items 1–4 are safe to bundle into a single commit.  Item 5 trades display
latency for throughput; only apply if frame-drop measurements show idle gaps
are significant.

---

## 6. What was already fixed (Phase 13.2 & 13.3)

- **Pixel-size Java-bridge cache** (Phase 13.2): `get_pixel_size_um()` result
  cached per live session; eliminated ~1.285 s cumulative overhead across 5
  calls.
- **`processEvents()` from worker threads** (Phase 13.2): disabled unsafe
  calls in the MMCORE_PLUS wait loops; eliminated ~8 s per live session.
- **`time.sleep()` on UI thread** (Phase 13.3): removed sleep from
  `napariUpdateLive`; the inner rate-limit guard now skips frames instead of
  blocking the UI thread.
