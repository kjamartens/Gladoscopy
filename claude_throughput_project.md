# Glados throughput project

A standalone, self-contained work plan. You can be told **"work on
`claude_throughput_project.md`"** with no other context and execute it from this file
alone.

---

## 1. What this is and why it exists

Glados feels bloated and slow next to plain `pymmcore-plus` / `pycromanager`, even
though the design intent is that the backend does the recording and Glados merely hooks
onto it in real time.

Four read-only audits (acquisition/storage, threading/Qt, node dispatch, GUI-thread
inventory) found that this is not one bottleneck. It is **one pattern repeated at every
layer**:

> Work that should happen once per acquisition happens once per frame, and work that
> belongs to one thread is done by whichever thread happens to be holding it.

A single frame's journey today, for illustration:

```text
camera -> pymmcore-plus MDA thread (Qt.DirectConnection = SYNCHRONOUS on the acq thread)
   |- metadata_refactor()            fresh OrderedDict per frame
   |- _try_write_frame_to_zarr()     searchsorted per dim, then a ZSTD-COMPRESSED
   |                                 single-frame chunk written to its own file on disk
   \- put_data_in_..._queues()       O(n^2) rescan + fresh list alloc per frame
          |
          v  deque(maxlen=10), gated `if len(q) < 1` -> effective depth 1
   vis worker: builds an 8-key dict (6 keys constant) and fires a cross-thread Qt
   signal PER FRAME, including for frames the GUI will immediately drop
          |
          v
   GUI thread (napariUpdateLive): a hardware get_exposure() call, metadata_refactor()
   AGAIN (result unused), searchsorted x dims twice, a SECOND zarr write of the same
   frame, N x set_current_step (each = re-slice + zstd decompress + contrast rescan +
   GPU upload), full-frame memcpy, refresh()
```

Meanwhile the GUI thread is also servicing a 1 Hz timer that reloads PNGs from disk
several times per tick, a log widget that re-reads the entire log file twice a second,
and an `errorInfo` setter that walks every node in the graph on each assignment. And the
analysis threads deliberately sleep for as long as their last analysis took, halving RT
throughput by design.

Almost all of this is removable without changing what Glados does.

### Relationship to the other Claude files

- `claude_project.md` — the separate 19-phase optimization roadmap. **This project is
  independent of it.** Do not advance that roadmap while working here.
- `claude_issues.md` — bug inbox. If you find a *new* bug outside a task's scope, add it
  there rather than fixing it inline.
- `claude_decisions.md` — append an entry for any non-trivial choice made while executing
  a task (option A over B, something skipped, something deferred).

---

## 2. Operating protocol

**Follow this exactly.**

1. **Be on the right branch.** `git branch --show-current` must print
   `claude_optimization`. If not, `git checkout claude_optimization`. Never commit this
   work to `main`.
2. **Pick the next task.** Work top-down through the task index in section 4, skipping
   any task whose `Depends on` is not yet done. Respect the recommended order in section
   3. Do **not** batch tasks.
3. **Re-verify before editing.** Every line number in this file was anchored at commit
   `cd01032` and *will* drift. Each task gives a `Find:` symbol — locate that symbol with
   grep first and work from what you actually find. If the code no longer matches the
   task description, stop and report rather than forcing the edit.
4. **One task = one commit.** Use the `Commit:` line verbatim as the commit subject.
   Conventional-commits style. Add the trailer:
   `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
5. **Run the `Verify:` block before committing.** If it fails, fix or revert — do not
   commit a red state.
6. **Tick the box** in the section 4 index (`- [ ]` to `- [x]`) in the same commit.
7. **Log decisions** in `claude_decisions.md` in the same commit when the task involved a
   judgement call.
8. **Stop at the marked stop points** (section 3) and wait for the user.
9. Tasks marked **(decision)** must not be implemented without asking the user first.

### Baseline verification

Unless a task says otherwise, `Verify:` means at minimum:

```bash
pytest -q
```

The suite is around 341 tests and must stay green. There is no lint gate that blocks;
`make lint` is informational.

Many tasks also list a manual check. The app launches with:

```bash
make run-demo     # pymmcore-plus bundled demo camera, no backend popup
make run          # normal launch with the backend chooser
```

If no hardware or demo backend is available in your environment, run `pytest -q`, state
plainly in your report that the manual check could not be performed, and do not claim
otherwise.

---

## 3. Threading invariants

These are the point of the whole project. Half the tasks below simply enforce them.
They are also recorded in `CLAUDE.md` under *Architecture -> Threading model* (task
**T-0.1**, already done).

1. **The Qt/GUI thread is holy.** It paints, lays out, and handles input. It must not
   touch hardware, block on I/O, or run analysis. Anything else belongs on a worker.
2. **All microscope access goes through one owner.** `MILcore` / `core` has exactly one
   owning thread; other threads submit requests. Unsynchronized cross-thread `core.*`
   calls caused the JVM fatal crash fixed in commit `cd01032`.
3. **Only the GUI thread touches napari.** Workers emit Qt signals to a bridge object;
   they never mutate `viewer.layers` or `viewer.dims` directly.

### Recommended execution order

```text
T-0.1
  -> Tier A, tasks A1..A6      (small, independent, de-risk everything after)
  -> T-B1                      (one file; closes the crash class before more concurrency)
  -> T-A7                      (ring buffer)          [STOP POINT]
  -> Tier C  (C1, C2, C3, C4)                         [STOP POINT after C3]
  -> Tier D  (D5, D6, D7 first - small; then D1, D2, D3, D4)
  -> Tiers E, F, G, H in any order
  -> T-D8                      (NDTiff storage; informs and may shrink T-E6)
  -> T-E6                      (only after Tier E, Tier F and T-D8; re-measure first)
  -> T-B3 (after C3), then T-B4
  -> T-G10 (decision), T-F8 scope (decision)          [STOP POINTS]
```

**Stop points** — finish the task, commit, then stop and report to the user:

- after **T-A7** (the frame transport changes shape)
- after **T-C3** (live mode stops using the MDA engine; wants a real-hardware smoke test)
- before **T-B3** (largest single refactor in the plan)
- before **T-G10** and before the `LaserControlScripts.py` half of **T-F8** (both are
  behaviour changes needing the user's call)

---

## 4. Task index

Legend — Size: S = under approx. 30 lines changed, M = one file, L = architectural.

### Tier 0 — Setup

- [x] **T-0.1** Document the threading invariants in `CLAUDE.md` — S, no deps

### Tier A — Frame transport (the spine)

- [x] **T-A1** Delete unused per-frame `metadata_refactor` — S, no deps
- [x] **T-A2** Remove the O(n^2) queue fan-out — S, no deps
- [x] **T-A3** Gate frames before the thread hop — M, no deps
- [x] **T-A4** Display-path micro-fixes — S, no deps
- [x] **T-A5** Delete dead per-frame signals and helpers — S, no deps
- [x] **T-A6** Gate eager per-frame log formatting — S, no deps
- [x] **T-A7** Ring buffer; acquisition callback becomes a pure hand-off — **L**, needs A1-A3

### Tier B — Hardware ownership

- [x] **T-B1** Serialize all MIL access behind a re-entrant lock — M, no deps
- [ ] **T-B2** Mirror hardware constants into `shared_data`; display never calls MIL — M, needs B1
- [ ] **T-B3** `MicroscopeService` owner thread — **L**, needs B1, B2, C3 — **stop point**
- [ ] **T-B4** Migrate GUI slots to submit intents — L, incremental, needs B3

### Tier C — Live mode is a 999-frame MDA

- [x] **T-C1** Continuous-sequence primitives in MIL — M, needs B1
- [x] **T-C2** `live_mode_method` / `live_pull_policy` settings — S, needs C1
- [x] **T-C3** `run_liveSequence_worker` — **L**, needs C1, C2, A7 — **stop point**
- [x] **T-C4** Guard `multiDstack` + live — S, needs C3

### Tier D — Storage

- [x] **T-D1** One store-creation site with an explicit dtype — M, no deps
- [x] **T-D2** Stop writing every frame to zarr twice — S, needs D1
- [x] **T-D3** Writer thread with amortized chunks — **L**, needs A7, D1 — *step 2 (chunking) measured and rejected; see decisions*
- [x] **T-D4** Delete the O(N*M) backfill pass — M, needs D3 — *kept but made O(1)-per-event and skipped without NDTiff; see decisions*
- [x] **T-D5** Fix the `id()`-keyed dimension cache — S, no deps
- [x] **T-D6** Fix `zarr.open(<Array>)` always failing — S, no deps
- [x] **T-D7** Fix `TemporaryDirectory` lifetimes — S, no deps
- [ ] **T-D8** Offer NDTiff as a pymmcore-plus storage format; benchmark tuned OME-Zarr/OME-TIFF against it — M, no deps — *do before T-E6*

### Tier E — Napari visualisation

- [x] **T-E1** Batch per-dimension `set_current_step` calls — M, no deps
- [x] **T-E2** Throttle auto-contrast on the multiDstack path — S, no deps
- [x] **T-E3** Stop per-frame layer teardown/rebuild — M, no deps
- [x] **T-E4** Preallocate album-mode layers — M, no deps
- [x] **T-E5** Re-measure the many-layers cliff — S, needs E1-E4
- [ ] **T-E6** Take zarr off the live display path during an MDA — **L**, needs E1-E5, F1-F5 — *open: display repaints only 2-3x/s on MMCORE_PLUS*

### Tier F — Keep the GUI thread holy

- [x] **T-F1** Memoize `findIconFolder()` and cache pixmaps — M, no deps
- [x] **T-F2** Stop loading a PNG from disk inside `NodeItem.paint()` — M, needs F1
- [x] **T-F3** Tail-follow the log file instead of re-reading it — M, no deps
- [x] **T-F4** Coalesce the nodz timer and gate it on acquisition — M, needs F1
- [x] **T-F5** Fix O(nodes x scene items) `checkNodesOnErrors` on mouse-move — M, needs F1
- [x] **T-F6** Debounce resize rebuilds; fix the `QScrollArea` leak — M, no deps
- [x] **T-F7** Remove the synthetic resize + `processEvents()` — S, no deps
- [ ] **T-F8** `textChanged` to `editingFinished` + debounce — M, no deps — **partly a decision**
- [x] **T-F9** `NapariBridge` for worker-to-GUI layer updates — **L**, no deps
- [ ] **T-F10** Make the live/MDA toggle non-blocking — M, no deps

### Tier G — Analysis dispatch

- [ ] **T-G1** Cache `__function_metadata__()` on the registry — M, no deps
- [ ] **T-G2** Coerce kwarg values at bind time — M, needs G1
- [ ] **T-G3** Resolve Variable kwargs to closures — M, needs G1
- [ ] **T-G4** `BoundNode`; delete the three per-frame `eval()` sites — **L**, needs G1-G3
- [ ] **T-G5** Opt-in subprocess state snapshots — M, no deps
- [ ] **T-G6** Probe metadata picklability once, not per frame — S, no deps
- [ ] **T-G7** Drop the duty-cycle sleep in the subprocess proxy — S, no deps
- [ ] **T-G8** Pass the dimension map as init context — M, no deps
- [ ] **T-G9** Fix the thread leak on RT-node stop — M, no deps
- [ ] **T-G10** **(decision)** Invert the subprocess default — needs G5, G7 — **stop point**

### Tier H — MDA GUI

- [ ] **T-H1** Debounce `get_MDA_events_from_GUI` — M, no deps
- [ ] **T-H2** Keep `to_pycromanager()` lazy until acquisition start — M, needs H1
- [ ] **T-H3** Move `set_focus_device` out of the keystroke path — S, needs H1

---

## 5. Tasks

### T-0.1 — Document the threading invariants in CLAUDE.md

Tier: 0 | Depends on: none | Risk: none | Size: S

**Why:** These three rules are the durable output of this project; every future session
needs them, and half the tasks below only make sense in their light.

**Files:** `CLAUDE.md`

**Find:** the `## Architecture` section.

**Do:**

1. Add a `### Threading model` subsection under `## Architecture`, containing the three
   invariants from section 3 of this file, stated in the terse factual style used
   elsewhere in `CLAUDE.md`.
2. For invariant 2, cite commit `cd01032` as the concrete precedent (two threads drove
   the same `core.mda`/`Acquisition` object and produced a native access violation / JVM
   fatal crash) and note that `pyjavaz`'s `Bridge.send_and_receive` already holds a single
   global `_communication_lock` per round trip, so on the Java backend all hardware
   traffic is serialized regardless of which thread calls it.
3. Add one line pointing at `claude_throughput_project.md` as the standalone plan that
   enforces these.

**Don't:** Don't restructure existing `CLAUDE.md` sections. Don't add the task list.

**Verify:** `pytest -q`. Read back the section and confirm it stands alone.

**Commit:** `docs(claude): document GUI-thread and hardware-ownership threading invariants`

---

### T-A1 — Delete unused per-frame metadata_refactor

Tier: A | Depends on: none | Risk: low | Size: S

**Why:** In the `frameByFrame` branch the refactored metadata is computed on the GUI
thread on every displayed frame and never read; on the MMCORE_PLUS backend it is also a
*second* refactor of metadata that `grab_image_liveVis_PyMMCore` already refactored.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** `def _napariUpdateLive_locked` (approx. line 186). Inside it, the
`frameByFrame` branch, approx. line 190:
`metadata = utils.metadata_refactor(DataStructure['data'][1],shared_data)`

**Do:**

1. Confirm by grep that `metadata` is genuinely unused for the remainder of the
   `frameByFrame` branch (it is used in the `multiDstack` branch — leave that one alone).
2. Delete the assignment.

**Don't:** Don't touch the `multiDstack` branch's `metadata_refactor` call. Don't remove
`metadata_refactor` itself.

**Verify:** `pytest -q`. Then `make run-demo`, start live mode, confirm the image still
displays with correct contrast and colormap.

**Commit:** `perf(live): drop unused per-frame metadata refactor in frameByFrame branch`

---

### T-A2 — Remove the O(n^2) queue fan-out

Tier: A | Depends on: none | Risk: low | Size: S

**Why:** Every frame, each caller builds a throwaway list of queues, and the callee then
rescans `shared_data.RTAnalysisQueuesThreads` **by object identity** to recover the very
thread that owns the queue it was just handed. There is also a latent `TypeError`.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** `def put_data_in_visualisation_and_analysis_queues` (approx. line 526). Its
four call sites pass `[item['Queue'] for item in self.shared_data.RTAnalysisQueuesThreads]`
— grep for `put_data_in_visualisation_and_analysis_queues(` to find all of them.

**Do:**

1. Change the signature to take `analysis_entries` (the `RTAnalysisQueuesThreads` list
   itself) instead of `analysis_queues`.
2. Replace the nested loop with a single pass over `analysis_entries`, reading
   `entry['Queue']` and `entry['Thread']` directly. Preserve the existing
   `if len(queue) < 1` drop-gate and the `thread.new_image()` call exactly.
3. Update all four call sites to pass `self.shared_data.RTAnalysisQueuesThreads`.
4. Fix the timing block at the end: `end = time.perf_counter()` currently runs
   unconditionally while `start` is `None` when DEBUG is off. Compute `end` only inside
   the `isEnabledFor(logging.DEBUG)` guard, reusing the `debug_enabled` flag already
   computed above rather than calling `isEnabledFor` a second time.

**Don't:** Don't change the drop-gate semantics (`if len(queue) < 1`) — deeper queueing
was measured and rejected; see `docs/bench-live-display.md`. Don't remove the `break`
semantics such that a queue receives two frames.

**Verify:** `pytest -q`. Then `make run-demo`, start live mode with one RT-analysis node
active, confirm the node still receives frames (its overlay updates).

**Commit:** `perf(transport): iterate RT analysis queues once per frame`

---

### T-A3 — Gate frames before the thread hop

Tier: A | Depends on: none | Risk: medium | Size: M

**Why:** The visualisation worker builds an 8-key dict (6 of the keys are constants) and
fires a cross-thread Qt signal for **every** queued frame — including the frames that
`napariUpdateLive` then immediately drops at its own fps/exposure gate. The marshalling
cost is paid for frames that are never drawn.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** `def run_napariVisualisation_worker` (approx. line 975) for the producer, and
`def napariUpdateLive` (approx. line 125) for the gate (the `min_delay_time` /
`last_display_update_time` logic).

**Do:**

1. Extract the fps/exposure rate-limit decision from `napariUpdateLive` into a small
   helper, e.g. `_should_display_now(shared_data) -> bool`, that both sides can call.
2. In the worker loop, call that helper before constructing the payload; if it returns
   `False`, drop the frame and continue without yielding.
3. Hoist the six constant keys (`napariViewer`, `core`, `layer_name`, `layer_color_map`,
   the two empty lists, `finalisationProcedure`) out of the loop — build the dict once
   before the loop and update only `data` and `acqState` per iteration.
4. Leave the gate in `napariUpdateLive` in place as a second line of defence; it is
   cheap once the worker already filtered.

**Don't:** Don't change the `finalisationProcedure` path or the post-loop drain blocks —
those yield deliberately different payloads. Don't reuse a single mutable dict across a
queued signal boundary if the receiver may lag; construct a fresh dict per yield from the
prebuilt constants (a shallow `dict(base)` copy is fine and still avoids re-deriving the
values).

**Verify:** `pytest -q`. Then `make run-demo`, live mode, confirm the frame rate is
unchanged or better and the display is still smooth. Toggle live off/on three times and
confirm no frames get stuck.

**Commit:** `perf(transport): drop frames in the vis worker instead of after the thread hop`

---

### T-A4 — Display-path micro-fixes

Tier: A | Depends on: none | Risk: low | Size: S

**Why:** Four small per-frame costs on the GUI thread, each trivially removable.

**Files:** `glados_pycromanager/GUI/napariGlados.py`,
`glados_pycromanager/GUI/sharedFunctions.py`

**Find:** Each location is named inline in the numbered steps below. Re-verify each
by symbol name before editing.

**Do:**

1. `napariGlados.py` approx. line 132, in `napariUpdateLive`:
   `np.min(((50/1000),(float(...)*0.99)/1000))` allocates a numpy array to compare two
   scalars. Replace with the builtin `min(...)`.
2. `def _maybe_refresh_contrast` (approx. line 104): the
   `int(shared_data.config.visualisation_config.contrast_refresh_every_n_frames)` parse
   runs per frame. Read it once and cache it on `shared_data` (invalidated when settings
   are saved), or at minimum hoist it out of the per-frame path.
3. `def _napariUpdateLive_locked`, `multiDstack` branch (approx. lines 371-384): two
   identical `np.searchsorted` loops compute the same per-dimension indices twice — once
   to build `sliceTuple`, once to set the napari dims step. Reuse `sliceTuple` for the
   second loop.
4. `sharedFunctions.py` `def __setattr__` (line 351): `Shared_data` overrides
   `__setattr__` purely to log, calling `logging.getLogger(__name__)` on **every**
   attribute write — 4 to 6 times per displayed frame. Remove the override entirely.

**Don't:** For item 4, if removing the override turns out to break a test that asserts on
the debug logging, hoist the logger to a module-level constant instead of deleting, and
note the deviation in `claude_decisions.md`.

**Verify:** `pytest -q`. Then `make run-demo`, live mode, confirm display and contrast
behave identically.

**Commit:** `perf(live): remove per-frame allocations and attribute-write logging`

---

### T-A5 — Delete dead per-frame signals and helpers

Tier: A | Depends on: none | Risk: low | Size: S

**Why:** Dead code that still costs work per frame, plus one silently-broken safety
mechanism.

**Files:** `glados_pycromanager/GUI/AnalysisClass.py`,
`glados_pycromanager/GUI/napariGlados.py`,
`glados_pycromanager/GUI/sharedFunctions.py`

**Find:** Each location is named inline in the numbered steps below. Re-verify each
by symbol name before editing.

**Do:**

1. `AnalysisClass.py` — `analysis_done_signal` is declared at lines 575 and 858 and
   emitted per frame per node at lines 793 and 927. **Grep the whole repo for
   `analysis_done_signal` — there are zero `connect()` calls.** Confirm this, then remove
   the declarations, the emits, and any payload built solely to feed them.
2. `napariGlados.py` — `def napariUpdateAnalysisThreads` (line 449) is referenced nowhere
   and calls `getLayerIdFromName` with the old 2-argument signature. Confirm by grep, then
   delete.
3. `sharedFunctions.py` line 245 — `liveUpdateEvent = pyqtSignal(object)` is never
   emitted. Confirm by grep, then delete.
4. `sharedFunctions.py` line 568 — `class periodicallyUpdate` is imported in two places
   and never instantiated. Confirm by grep, then delete the class and the two imports.
5. `sharedFunctions.py` line 30 — `class LoggingList` is never instantiated (`__init__`
   assigns a plain `[]` instead), so its `remove()` override, which is what would call
   `stop()`/`destroy()` on a removed analysis thread, **never runs**. The three
   `RTAnalysisQueuesThreads.remove(...)` call sites in `napariGlados.py` therefore skip
   thread teardown silently. **This one is a judgement call**: either wire `LoggingList`
   up properly, or delete it and make the teardown explicit at the three call sites.
   Prefer explicit teardown at the call sites (simpler, no magic). Record the choice in
   `claude_decisions.md`.

**Don't:** Don't delete `LoggingList` without replacing the teardown it was supposed to
provide — that would turn a silent bug into a leak. Note that **T-G9** also touches
analysis-thread shutdown; if G9 is already done, make this consistent with it.

**Verify:** `pytest -q`. Then `make run-demo`, start and stop an RT-analysis node three
times, and confirm via the Performance Mode panel's thread list that thread count returns
to baseline.

**Commit:** `refactor: remove dead per-frame signals and unused helpers`

---

### T-A6 — Gate eager per-frame log formatting

Tier: A | Depends on: none | Risk: low | Size: S

**Why:** `logging.debug(f"Analysis on Image done with result: {result}")` builds the
f-string — including a full numpy repr of the result array — on **every frame**,
regardless of the active log level.

**Files:** `glados_pycromanager/GUI/AnalysisClass.py`

**Find:** approx. line 1072, the `logging.debug(f"Analysis on Image done with result:` call.

**Do:**

1. Convert to lazy `%s` formatting: `logging.debug("Analysis on Image done with result: %s", result)`,
   or guard with `if logger.isEnabledFor(logging.DEBUG):` if the repr is expensive enough
   to matter even when lazily deferred (it is not, with `%s`).
2. While in this file, grep for other per-frame `logging.*(f"` calls in the analysis run
   loops and convert them the same way.

**Don't:** Don't change log levels or messages — only the formatting mechanism.

**Verify:** `pytest -q`. Set the log level to DEBUG in Advanced Settings and confirm the
message still appears with the same content.

**Commit:** `perf(rt-analysis): use lazy logging on the per-frame analysis path`

---

### T-A7 — Ring buffer; acquisition callback becomes a pure hand-off

Tier: A | Depends on: A1, A2, A3 | Risk: **high** | Size: **L (architectural)**

**Why:** `grab_image_liveVis_PyMMCore` is connected with `Qt.DirectConnection`, so it runs
**synchronously on pymmcore-plus's own MDA thread**. Everything it does happens in front
of the next camera frame: metadata refactoring, a compressed zarr chunk write to disk, and
the analysis fan-out. The camera thread should hand the frame off and return.

**Files:** `glados_pycromanager/GUI/napariGlados.py`, plus a new module
`glados_pycromanager/GUI/frame_ring.py`

**Find:** `def grab_image_liveVis_PyMMCore` (line 590), `def _try_write_frame_to_zarr`
(line 615), `def put_data_in_visualisation_and_analysis_queues` (line 526).

**Do:**

1. Add `frame_ring.py` with a small bounded single-producer ring buffer: fixed capacity
   (default 4), `push(image, metadata)` that overwrites the oldest entry when full and
   increments a `dropped` counter, `pop_latest()`, `pop_next()`, and a `threading.Event`
   the consumer can wait on. Keep it dependency-free and unit-testable.
2. Reduce `grab_image_liveVis_PyMMCore` to: check `self.acqstate`, `ring.push(image,
   metadata)`, return. Keep the existing broad `try/except` + `logging.exception` wrapper
   — a raised exception on a `DirectConnection` callback otherwise vanishes silently.
3. Move `metadata_refactor` and the analysis fan-out to a consumer that drains the ring on
   a worker thread.
4. Leave the zarr write where it is **for now** and let **T-D3** move it to the writer
   thread; note this explicitly in the commit body so the intermediate state is
   understood.
5. Expose the `dropped` counter through the Performance Mode panel if that is
   straightforward; otherwise log it once at acquisition end.

**Don't:** Don't change the `Qt.DirectConnection` — the comment in
`run_MILCoreAcquisition_worker` explains why polling `processEvents()` was removed and why
direct dispatch is required (the worker thread has no event loop of its own). Don't make
the ring unbounded. Don't let the consumer block the producer.

**Verify:** `pytest -q`, plus new unit tests for `frame_ring.py` covering overwrite,
drop-counting, and the empty case. Then `make run-demo`: live mode for 60 seconds with an
RT node active; confirm no frames stall, the display is smooth, and stopping live mode
terminates cleanly.

**Commit:** `perf(transport): hand frames to a bounded ring buffer from the camera callback`

**After this task: STOP and report to the user.**

---

### T-B1 — Serialize all MIL access behind a re-entrant lock

Tier: B | Depends on: none | Risk: medium | Size: M

**Why:** Commit `cd01032` exists because two threads drove the same core concurrently and
produced a **native access violation / JVM fatal crash**. Its `RLock` and
`_acq_transition_lock` are the **only two locks in the entire codebase**, against roughly
273 `MILcore.*` / `core.*` call sites. Hardware is touched from at least five thread
contexts: the GUI thread (94 sites in `MMcontrols.py` alone, plus all of
`LaserControlScripts.py`), the acquisition worker, RT-analysis QThreads
(`LaserAdjustment.py` calls `core.set_property()` **per frame**), nodz executor
`QRunnable`s (`AutoFocusBF.py` snaps and moves stages; `Strobo_lasers.py` writes serial
commands), and a `ThreadPoolExecutor` in `utils.forceReset`. Interleaving two threads'
serial writes to a TriggerScope is a hardware-correctness bug, not just a performance one.

On the Java backend this serialization already exists but is implicit: `pyjavaz`'s
`Bridge.send_and_receive` holds a single global `_communication_lock` for the whole round
trip. `PYCROMANAGER_PYTHON` and `MMCORE_PLUS` have **no** such lock.

**Files:** `glados_pycromanager/Core/microscopeInterfaceLayer.py`

**Find:** `class MicroscopeInterfaceLayer`, its `__init__`, and its public methods.

**Do:**

1. Add `self._hw_lock = threading.RLock()` in `__init__`.
2. Take the lock in every public method that touches `self.core`. Prefer a small private
   decorator applied to each method over 60 hand-written `with` blocks; keep it readable
   and make sure it preserves signatures and docstrings (`functools.wraps`).
3. Re-entrant is required: `get_image_width()` calls `get_roi()`, and other methods
   compose similarly.
4. Do **not** hold the lock across cache reads that never touch `self.core` (the
   `get_exposure` / `get_pixel_size_um` cache-hit fast paths) — return early before
   acquiring, so the display path is not serialized against a slow stage move.
5. Add a module docstring note explaining why the lock exists, citing `cd01032`.

**Don't:** Don't remove `napariHandler._acq_transition_lock` — it guards a different,
higher-level invariant (worker stop before start). Don't add a timeout to the lock;
a deadlock should be diagnosed, not silently skipped.

**Verify:** `pytest -q`, plus a new test asserting re-entrancy (a MIL method that calls
another MIL method does not deadlock — `get_image_width()` on the fake MIL is the natural
case; extend `tests/fakes/fake_mil.py`). Then, if hardware or the demo backend is available:
**stress the case that caused the crash** — rapid Live/MDA toggling while also moving a
stage and changing a config group. This is the real test.

**Commit:** `fix(mil): serialize all hardware access behind a re-entrant lock`

---

### T-B2 — Mirror hardware constants into shared_data

Tier: B | Depends on: B1 | Risk: low | Size: M

**Why:** `napariUpdateLive` calls `shared_data.MILcore.get_exposure()` **on the GUI thread,
per displayed frame** — the code's own comment reads *"This is on the main thread, so we
don't want to unnecessarily wait."* It is cached today, but the display path should never
reach for MIL at all. Same for the two `get_pixel_size_um()` calls on layer creation.

**Files:** `glados_pycromanager/GUI/sharedFunctions.py`,
`glados_pycromanager/GUI/napariGlados.py`,
`glados_pycromanager/Core/microscopeInterfaceLayer.py`

**Find:** `napariGlados.py` line 132 (`get_exposure` in the rate-limit gate) and the
`get_pixel_size_um()` calls in the layer-creation paths (grep
`get_pixel_size_um` within `napariGlados.py`).

**Do:**

1. Add plain mirrored fields on `Shared_data`: `hw_exposure_ms`, `hw_pixel_size_um`,
   `hw_image_shape`, `hw_roi`.
2. Refresh them from MIL at the points where they can change: acquisition start,
   `set_exposure`, `set_roi` / `clear_roi`, and backend/core binding. The existing
   `invalidate_exposure_cache` / `invalidate_pixel_size_cache` call sites show exactly
   where those points are.
3. Change the display path to read the mirrored fields only.

**Don't:** Don't remove the MIL-level caches — they still serve non-display callers.
Don't refresh the mirror on a timer; refresh on the events that change it.

**Verify:** `pytest -q`. Then `make run-demo`: change the exposure while live mode is
running and confirm the display rate-limit adapts; change ROI and confirm the layer
rebuilds with the right scale.

**Commit:** `perf(live): read mirrored hardware constants instead of calling MIL per frame`

---

### T-B3 — MicroscopeService owner thread

Tier: B | Depends on: B1, B2, C3 | Risk: **high** | Size: **L (architectural)**

**Do not start this without checking in with the user first.**

**Why:** T-B1 makes hardware access safe but not fair: on the Java backend every call
costs approximately 257 ms measured, so a GUI-thread `get_position()` directly steals
bandwidth from the frame path, in arbitrary order. Giving the hardware one owner thread
lets the frame path be prioritised and lets GUI slots stop blocking entirely.

**Files:** new `glados_pycromanager/Core/microscope_service.py`;
`glados_pycromanager/Core/microscopeInterfaceLayer.py`;
`glados_pycromanager/GUI/napariGlados.py`

**Find:** `class MicroscopeInterfaceLayer` and the `self._hw_lock` added by T-B1; the
live pull loop added by T-C3 in `napariGlados.py`.

**Do:**

1. `MicroscopeService`, a `QObject` moved onto a dedicated `QThread`, owning the `MILcore`
   instance.
2. A priority request queue: high for frame-path needs, normal for UI intents. Replies via
   queued `pyqtSignal`.
3. **T-C3's pull loop becomes the service's streaming mode** — the thread that owns the
   hardware is the thread that pulls the frames, so there is no extra hop added to the
   frame path.
4. A `core` proxy object exposing the current synchronous API but submitting to the
   service and blocking **the caller's** thread. Node code already runs off the GUI
   thread, so no node has to change.
5. GUI callers must use the non-blocking submit path; that migration is **T-B4**.

**Don't:** Don't migrate all 273 call sites in this task. Land the service, the proxy, and
the acquisition + RT paths only. Don't let the GUI thread ever block on a service reply.

**Verify:** `pytest -q` plus new tests for queue priority and proxy round-trip. Full
manual smoke test on real hardware across all three backends.

**Commit:** `feat(mil): add MicroscopeService owner thread with a priority request queue`

---

### T-B4 — Migrate GUI slots to submit intents

Tier: B | Depends on: B3 | Risk: medium | Size: L (incremental)

**Why:** Completes invariant 1. See **T-F8** for the specific slots that hurt most.

**Files:** `glados_pycromanager/GUI/MMcontrols.py`,
`glados_pycromanager/GUI/LaserControlScripts.py`,
`glados_pycromanager/GUI/FlowChart_dockWidgets.py` (`createCoreVariables`)

**Find:** The blocking slots listed in T-F8, plus `def createCoreVariables` in
`FlowChart_dockWidgets.py` (approx. line 3499). Grep each file for `MILcore.` and
`core.` to enumerate the rest.

**Do:** One file per commit. For each slot: submit the intent, disable the widget,
re-enable on the reply signal. Start with the blocking ones listed in T-F8.

**Don't:** Don't do this before T-B3. Don't convert node-side `core.*` calls — they are
correctly synchronous on their own worker threads.

**Verify:** `pytest -q` plus manual exercise of each migrated control.

**Commit:** `refactor(mmcontrols): submit hardware intents instead of blocking the GUI thread`

---

### T-C1 — Continuous-sequence primitives in MIL

Tier: C | Depends on: B1 | Risk: medium | Size: M

**Why:** Glados has no live mode — it has a 999-frame MDA restarted in a `while` loop.
MIL exposes only `snap_image()`, `get_image()` and `stop_sequence_acquisition()`; none of
the circular-buffer primitives that MM's own live window, napari-micromanager and any
plain pycromanager script are built on. This task adds them; **T-C3** uses them.

**Files:** `glados_pycromanager/Core/microscopeInterfaceLayer.py`, `tests/fakes/fake_mil.py`

**Find:** the existing three-branch `self._mi` dispatch pattern, e.g. `def get_exposure`
(line 286) and `def stop_sequence_acquisition` (line 724).

**Do:** Add these methods, following that dispatch pattern exactly. The per-backend APIs
below were **verified against the installed stack** (pymmcore 12.5.0.75.0, pymmcore-plus
0.18.1, pycromanager 1.0.2) — do not substitute from memory:

| MIL method | MMCORE_PLUS | PYCROMANAGER_PYTHON (see note) | PYCROMANAGER_JAVA (see note) |
| --- | --- | --- | --- |
| `start_continuous_sequence_acquisition(interval_ms=0)` | `startContinuousSequenceAcquisition(0)` | `start_continuous_sequence_acquisition(0)` | same |
| `is_sequence_running()` | `isSequenceRunning()` | `is_sequence_running()` | same |
| `get_remaining_image_count()` | `getRemainingImageCount()` | `get_remaining_image_count()` | same |
| `pop_next_image_and_metadata()` | `popNextImageAndMD()` returns `(ndarray, Metadata)` | `pop_next_tagged_image()` returns `TaggedImage` | `pop_next_tagged_image()` |
| `get_last_image_and_metadata()` | `getLastImageAndMD()` | `get_last_image_md(0, 0, md)` | `get_last_tagged_image()` |
| `clear_circular_buffer()` | `clearCircularBuffer()` | `clear_circular_buffer()` | same |

Notes:

- **PYCROMANAGER_PYTHON:** `pycromanager.Core()` under `start_headless(python_backend=True)`
  returns mmpycorex's `CMMCoreSnakeCase`, a subclass of `pymmcore.CMMCore` carrying
  **both** casings plus injected `pop_next_tagged_image` / `get_tagged_image` shims
  (`.venv/Lib/site-packages/mmpycorex/launcher.py:28-84,224-235`). It is *not*
  camelCase-only.
- **PYCROMANAGER_JAVA:** `ZMQRemoteMMCoreJ` is a `JavaObject` created with
  `convert_camel_case=True`, so snake_case names work over the bridge.

Additional work in the same task:

1. Normalise every return to `(2-D np.ndarray, dict)` inside MIL so callers are
   backend-blind. Build the dict from `.tags` for the tagged-image backends; convert the
   `Metadata` object once for `popNextImageAndMD`.
2. Reshape defensively when the returned pixel buffer has `ndim == 1`, using a new
   `_image_shape_cache` field. Follow the existing cache idiom exactly: initialise in
   `__init__`, invalidate in `set_core()`, `set_roi()` and `clear_roi()`, and add an
   `invalidate_image_shape_cache()` method to match `invalidate_exposure_cache`.
3. Fix `def get_image` (approx. line 327) while here: `np.reshape(..., newshape=...)` —
   the `newshape` keyword was removed in NumPy 2.1 and this project pins numpy 2.2.6.
   Use the positional form. Also collapse the three separate Java-bridge attribute
   fetches (`.pix`, `.tags["Height"]`, `.tags["Width"]`) to one plus the cached shape.
4. Extend `tests/fakes/fake_mil.py` with the new primitives and add per-backend dispatch tests
   following the existing MIL dispatch test pattern.

**Don't:** Don't call these from anywhere yet — T-C3 does that. Don't guess at method
names for a backend you cannot verify; if the installed version differs from the table,
stop and report.

**Verify:** `pytest -q` including the new dispatch tests.

**Commit:** `feat(mil): add continuous sequence-acquisition primitives for all backends`

---

### T-C2 — live_mode_method and live_pull_policy settings

Tier: C | Depends on: C1 | Risk: low | Size: S

**Why:** T-C3 changes how live mode fundamentally works. A config switch makes any
regression one dropdown away from being ruled out.

**Files:** `glados_pycromanager/GUI/sharedFunctions.py`

**Find:** `class MDAConfig` (line 87) and the `setting(...)` helper used by its fields.

**Do:**

1. Add `live_mode_method: str = setting("sequence", ...)` with allowed values `sequence`
   and `mda`, default `sequence`.
2. Add `live_pull_policy: str = setting("latest", ...)` with allowed values `latest` and
   `sequential`, default `latest`. Help text: `latest` shows the newest frame and cannot
   overflow the circular buffer; `sequential` delivers every frame in order and can.
3. Update the help text of the existing `live_mode_nr_frames` to say it applies only when
   `live_mode_method == 'mda'`.

**Don't:** Don't wire them to behaviour yet — T-C3 and T-C4 do.

**Verify:** `pytest -q`. Open Advanced Settings and confirm both new settings appear,
persist across a restart, and round-trip through the config JSON.

**Commit:** `feat(config): add live_mode_method and live_pull_policy settings`

---

### T-C3 — run_liveSequence_worker

Tier: C | Depends on: C1, C2, A7 | Risk: **high** | Size: **L (architectural)**

**Why:** This is the core architectural fix. Today live mode is
`run_mda(MDASequence(time_plan={"interval": 0.0, "loops": 999}))` on MMCORE_PLUS — so
every preview frame is driven through `MDAEngine` with a pydantic-validated `MDAEvent`.
The committed profiles show `_iter_exec_output`, `exec_sequenced_event` and pydantic
dominating, which `docs/perf-runtime-recipe.md` wrote off as *"not addressable without
upstream patches"* — it is entirely addressable by not using the acquisition engine for a
preview. On PYCROMANAGER_JAVA it is worse: each live frame is written into an NDTiff
dataset and then **read back over the Java bridge** via `dataset.read_image(**axes)`
(logged as finding B1 in `docs/napari-vis-strategy.md`, never scheduled). And the whole
acquisition object is torn down and rebuilt every 999 frames, roughly every 17 s at 60 fps.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** `def run_MILCoreAcquisition_worker` (line 743) — the `if self.liveOrMda == 'live':`
branch and its `while self.acqstate:` loop.

**Do:**

1. Add `run_liveSequence_worker` alongside the existing worker:

```python
MIL.clear_circular_buffer()
MIL.start_continuous_sequence_acquisition(0)
try:
    while self.acqstate:
        if MIL.get_remaining_image_count() > 0:
            image, metadata = MIL.get_last_image_and_metadata()   # or pop_next, per policy
            ring.push(image, metadata)                            # T-A7's ring
        else:
            time.sleep(0.0005)
finally:
    MIL.stop_sequence_acquisition()
```

2. Honour `live_pull_policy`: `latest` uses `get_last_image_and_metadata()` followed by
   `clear_circular_buffer()`; `sequential` uses `pop_next_image_and_metadata()`.
3. Dispatch on `live_mode_method` in `run_MILCoreAcquisition_worker`: `sequence` selects
   the new worker, `mda` keeps the existing code path untouched.
4. Synthesise a minimal metadata dict so downstream code is unchanged: `Time`, `Exposure`,
   `PixelSize_um`, and `Axes: {'time': n}` with a monotonic counter. Verify
   `utils.metadata_refactor` accepts it.
5. Ensure the stop path is clean: `is_sequence_running()` must be `False` after stopping,
   and the existing `_acq_transition_lock` / `_worker_stopped_event` serialization from
   `cd01032` must still be honoured.

**Don't:** Don't touch the MDA path — real multi-D acquisition legitimately needs the
engine. Don't remove the legacy live path. Don't use this worker when
`vis_method == 'multiDstack'` — **T-C4** handles that.

**Verify:** `pytest -q` plus a test that `live_mode_method='mda'` still selects the legacy
worker. Then, on real hardware if available, all three backends: live start/stop five
times each; `is_sequence_running()` False after each stop; no orphaned acquisition; frame
rate visibly improved on PYCROMANAGER_JAVA in particular.

**Commit:** `feat(live): drive live mode from continuous sequence acquisition`

**After this task: STOP and report to the user.**

---

### T-C4 — Guard multiDstack plus live

Tier: C | Depends on: C3 | Risk: medium | Size: S

**Why:** The sequence path produces no MDAEvents and no real `Axes`, so the `multiDstack`
rendering branch — which indexes a zarr array by acquisition axes — cannot work with it.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** the `live_mode_method` dispatch added by T-C3.

**Do:** When `vis_method == 'multiDstack'` and live mode is starting, pick **one**
strategy and implement it consistently: either force `frameByFrame` for the duration of
live mode, or fall back to the legacy MDA-based worker. Log the decision at INFO with a
clear reason. Record which you chose and why in `claude_decisions.md`.

**Don't:** Don't silently produce black slices. Don't change MDA-mode `multiDstack`
behaviour.

**Verify:** `pytest -q`. Then set `vis_method='multiDstack'`, start live mode, confirm the
chosen fallback engages and is logged, and that MDA-mode `multiDstack` still renders.

**Commit:** `fix(live): guard multiDstack visualisation on the sequence live path`

---

### T-D1 — One store-creation site with an explicit dtype

Tier: D | Depends on: none | Risk: medium | Size: M

**Why:** There are two places that create the display zarr store and they disagree. The
fallback path calls `zarr.open(...)` with **no `dtype=`**, which on zarr 3.1.0 produces a
**float64** array — so every uint16 camera frame is upcast on write: 4x the bytes through
the compressor and on disk, and it defeats napari's contrast fast path. `_preinit_mda_zarr`
passes the dtype correctly. Which array you get depends on a race between the two.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** the `zarr.open(` call in `_napariUpdateLive_locked` (approx. line 319-329) and
`def _preinit_mda_zarr` (line 639).

**Do:**

1. Extract a single `_create_mda_zarr(shared_data, layer_name, shape, h, w, dtype)`
   helper. Derive dtype from the camera (`np.uint8` / `np.uint16` as `_preinit_mda_zarr`
   already does).
2. Make both sites call it. The fallback path must pass a real dtype.
3. Keep the chunk shape as-is here; **T-D3** changes chunking.

**Don't:** Don't change chunking or compression in this task. Don't remove
`_preinit_mda_zarr`.

**Verify:** `pytest -q`. Then run an MDA with `vis_method='multiDstack'` and assert the
created array's dtype matches the camera (log it, or check the store on disk). Confirm the
displayed image is not washed out.

**Commit:** `fix(storage): create the display zarr from one site with an explicit dtype`

---

### T-D2 — Stop writing every frame to zarr twice

Tier: D | Depends on: D1 | Risk: low | Size: S

**Why:** On MMCORE_PLUS with `multiDstack`, the same frame is written once from the
acquisition callback and again from the GUI thread, with the slice index recomputed
identically. The second write is a full chunk re-encode of identical data.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** the zarr write in `_try_write_frame_to_zarr` (line 615) and the one in
`_napariUpdateLive_locked` (approx. line 378).

**Do:** Establish a single writer. The acquisition-side write is the correct one to keep
(it captures every frame, not just displayed ones — that is exactly why it was added).
Remove the GUI-thread write, or make it conditional on backends where the acquisition-side
write does not run. Read the surrounding comments carefully before deciding: the
acquisition-side write exists specifically because the vis queue drops frames.

**Don't:** Don't remove the acquisition-side write. Don't create a state where some
backend writes no frames at all — check each backend path explicitly.

**Verify:** `pytest -q`. Then run a 2-channel / 3-timepoint / 3-z MDA on MMCORE_PLUS with
`multiDstack` and confirm every slice is populated (no black frames) when scrubbing the
dims sliders.

**Commit:** `perf(storage): write each frame to the display zarr once`

---

### T-D3 — Writer thread with amortized chunks

Tier: D | Depends on: A7, D1 | Risk: **high** | Size: **L (architectural)**

**Why:** Chunks are `[1, ..., 1, h, w]` — **one chunk per frame** — so every camera frame
becomes one chunk encode, one **Zstd compression**, and one `open()/write()/close()` of a
separate file, synchronously on the acquisition thread. A 20 000-frame MDA creates 20 000
files in a single temp directory, which is pathological on NTFS.

**Files:** `glados_pycromanager/GUI/napariGlados.py`, the `_create_mda_zarr` helper from
T-D1, possibly a new `glados_pycromanager/GUI/frame_writer.py`

**Find:** `def _try_write_frame_to_zarr` (approx. line 615) and the `chunks=` argument
in the `_create_mda_zarr` helper introduced by T-D1.

**Do:**

1. Move the zarr write onto a dedicated writer thread draining T-A7's ring (or a second
   ring dedicated to storage, so display drops do not cause storage drops).
2. Change chunking to span the fast-varying axis — at least 8 to 32 frames per chunk.
3. Set `compressors=None` (or a cheap codec such as lz4/blosc) for a scratch display
   store. Verify the chosen setting against the installed zarr version's API — zarr 3.x
   changed the compressor keyword.
4. Ensure the writer is drained and joined at acquisition end before anything reads the
   store.

**Done 2026-09-09, with step 2 deliberately NOT applied.** Steps 1, 3 and 4 are
implemented (`GUI/frame_writer.py`, `compressors=None`, drain-and-join in
`_stop_frame_ring_consumer`). Step 2 — multi-frame chunks — was **measured and
rejected**: napari paints a multiDstack layer by reading a slice out of this very
array, so chunk size is on the display path too, and even with perfectly batched
whole-chunk writes 8- and 32-frame chunks were slower to write *and* several times
slower to read than one frame per chunk. Full numbers in `claude_decisions.md`
(2026-09-09, T-D3). The store therefore still creates 1 file per frame; the NTFS
file-count concern is unaddressed and is logged in `claude_issues.md`.

**Don't:** Don't drop storage frames silently — count and log them. Don't let the writer
outlive the store's `TemporaryDirectory` (see T-D7).

**Verify:** `pytest -q`. Then a long MDA (at least 2000 frames): confirm every slice is
populated, confirm the file count in the store directory dropped by roughly the chunk
factor, and confirm the acquisition-thread frame rate improved.

**Commit:** `perf(storage): write frames from a dedicated thread with amortized chunks`

---

### T-D4 — Delete the O(N*M) backfill pass

Tier: D | Depends on: D3 | Risk: medium | Size: M

**Why:** The finalisation block is O(N_events x M_rendered) dict-subset comparisons, with
a `time.sleep(0.001)` **per missing frame** and a random NDTiff `read_image()` per missing
frame — and it runs on the **GUI thread**. Because the vis worker is fps-throttled, most
frames are "missing", so this reads back nearly the whole acquisition one frame at a time.
For a large MDA it is a multi-second freeze at the end of every run. Once T-D3 writes every
frame at acquisition time, there is nothing to backfill.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** in `_napariUpdateLive_locked`, the `finalisationProcedure` branch (approx. lines
395-440), the loop over `shared_data._mdaModeParams`, and the `time.sleep(0.001)` whose
comment reads *"Can't explain why, but a sleep of 1 ms is super important for stability"*.

**Do:**

1. Confirm T-D3 genuinely writes every frame (add a counter and check it against the
   expected event count on a test acquisition) **before** deleting anything.
2. Remove the backfill loop and the now-unused `shared_data.allMDAslicesRendered` dict
   (grep for other readers first).
3. Keep a final `layer.refresh()` and dims update so the completed stack renders.

**Don't:** Don't delete this until T-D3 is verified — the sleep is papering over a real
race and removing the backfill without full-coverage writes will produce black slices.
If T-D3 cannot guarantee full coverage, convert `allMDAslicesRendered` to a `set` of
frozen axes tuples for O(1) membership and drop only the sleep, and record that in
`claude_decisions.md`.

**Verify:** `pytest -q`. Then a 2-channel / 3-t / 3-z MDA: no freeze at the end, every
slice populated when scrubbing.

**Commit:** `perf(storage): drop the O(N*M) slice backfill pass`

---

### T-D5 — Fix the id()-keyed dimension cache

Tier: D | Depends on: none | Risk: low | Size: S

**Why:** The cache key is `id(params)` — a memory address. CPython reuses addresses
routinely, so after one acquisition's params list is freed a new list can land at the same
address and the cache silently returns the **previous** acquisition's dimension map. Every
`sliceTuple`, the zarr shape, and the dims stepping all derive from it.

**Files:** `glados_pycromanager/GUI/napariGlados.py`,
`glados_pycromanager/GUI/sharedFunctions.py`

**Find:** `def _get_cached_dimensions` (line 77) and `cache_key = id(params)`.

**Do:** Replace the `id()` key with explicit invalidation: add a monotonically increasing
acquisition counter on `Shared_data`, bumped in the `_mdaModeParams` setter, and key the
cache on that. Invalidating directly in the setter is equally acceptable and simpler —
prefer whichever fits the existing property code.

**Don't:** Don't keep `id()` as a fallback.

**Verify:** `pytest -q` plus a regression test: set `_mdaModeParams` to two different
lists and assert the cached dimensions change. Then run two different-shaped MDAs
back-to-back and confirm the second renders with its own dimensions.

**Commit:** `fix(mda): key the dimension cache on acquisition identity, not id()`

---

### T-D6 — Fix zarr.open(<Array>) always failing

Tier: D | Depends on: none | Risk: low | Size: S

**Why:** `MDA_acq_finished` falls back to `zarr.open(self.shared_data.mdaZarrData['MDA'])`,
but `mdaZarrData['MDA']` is already a `zarr.Array`, not a store path. On zarr 3.x this
raises `TypeError: Unsupported type for store_like: 'Array'`, which is swallowed by the
`except (KeyError, Exception)` immediately below. The result: `self.data is None` on
**every** MMCORE_PLUS acquisition, and every downstream Nodz node consuming
`variablesNodz['data']` gets `None`.

**Files:** `glados_pycromanager/Core/MDAGlados.py`

**Find:** `def MDA_acq_finished` (line 1362) and the `zarr.open(...)` at line 1382.

**Do:**

1. Use the `zarr.Array` directly instead of re-opening it.
2. Fix the exception handler: `except (KeyError, Exception)` is redundant — `Exception`
   already covers `KeyError` — and it hides real failures. Catch the specific exceptions
   expected here and let the rest propagate or be logged at ERROR.
3. Check the nearby `self.data.path` usage (approx. line 1871), which raises
   `AttributeError` on this path for the same reason; make `storage_path` derive from
   something real.

**Don't:** Don't broaden the exception handling further.

**Verify:** `pytest -q`. Then run an MDA on MMCORE_PLUS and confirm `self.data` is not
`None` afterwards, and that a Nodz node consuming the acquisition data receives an array.

**Commit:** `fix(mda): stop re-opening an already-open zarr array on acquisition finish`

---

### T-D7 — Fix TemporaryDirectory lifetimes

Tier: D | Depends on: none | Risk: medium | Size: S

**Why:** Two separate lifetime bugs. (a) `tempfile.TemporaryDirectory()` is constructed and
immediately discarded, so its finalizer deletes the directory, then `os.makedirs`
recreates it — leaving a directory with no cleanup owner. (b) `shared_data.mdaZarrTempDir`
holds exactly **one** `TemporaryDirectory`, and two sites overwrite it — so starting a
second MDA drops the first object, whose finalizer then `rmtree`s a store that a live
napari layer is still pointing at.

**Files:** `glados_pycromanager/GUI/napariGlados.py`,
`glados_pycromanager/GUI/MMcontrols.py`, `glados_pycromanager/GUI/sharedFunctions.py`

**Find:** grep for `TemporaryDirectory()` across `glados_pycromanager/`. The
constructed-and-discarded pattern is in `PyMMCore_startedAcqCallback` (line 684, look for
`str(tempfile.TemporaryDirectory().name)`) and around `MMcontrols.py` line 739. The single
slot is `shared_data.mdaZarrTempDir`.

**Do:**

1. Hold every `TemporaryDirectory` object for as long as its directory is needed — assign
   it to a field, never to a discarded temporary.
2. Make the store's temp directory lifetime match the layer that references it: either
   keep a list/dict of live temp dirs keyed by layer name, or tear down the layer when the
   store goes.
3. While here, add a short comment (or a `claude_issues.md` entry) recording that
   MMCORE_PLUS ignores the user's Storage folder entirely — `savefolder`/`savename` are
   computed and never used on that branch, and `pyMMCdataset` is created but never written
   to. Do not fix that here; it is a separate change.

**Don't:** Don't switch to a permanent directory without a cleanup path —
`cleanUpTemporaryFiles` exists and should stay authoritative.

**Verify:** `pytest -q`. Then run two MDAs back-to-back and confirm the first acquisition's
layer still renders after the second starts, and that temp directories are cleaned on exit.

**Commit:** `fix(storage): keep temporary store directories alive for their layer's lifetime`

---

### T-D8 — Offer NDTiff as a pymmcore-plus storage format (and probably default to it)

Tier: D | Depends on: none (T-D1/T-D2/T-D3 already landed) | Risk: medium | Size: M | **Do before T-E6**

**Why:** `MDAConfig.mmcore_save_format` currently offers `ome-zarr`, `ome-tiff`
and `none`, all written by pymmcore-plus' own `run_mda(output=...)`. NDTiff — the
format the pycromanager backends already produce — is not among them, and on the
measurements below it is not a lateral choice, it is **far** faster than either.

Benchmarked on this machine, 1000 frames of 256x256 uint16 (128 KB each, 131 MB
total), written one frame at a time as the acquisition path does, then random
single-frame reads as scrubbing does:

| store | write | throughput | files | random read |
|---|---|---|---|---|
| zarr chunk=1 (the scratch display store) | 6.50 ms/frame | 20 MB/s | 1001 | 3.41 ms |
| **NDTiff (`ndstorage.NDTiffDataset.put_image`)** | **0.35 ms/frame** | **379 MB/s** | **2** | **0.10 ms** |
| `run_mda(output=…​.ome.zarr)` | 3.43 ms/frame | 38 MB/s | 1002 | – |
| `run_mda(output=…​.ome.tiff)` | 6.97 ms/frame | 19 MB/s | 1 | – |

**19x faster to write and 34x faster to read than the scratch zarr, in 2 files
instead of 1001.** The zarr formats are limited by per-file overhead — one file
per frame — which is exactly the cost identified in T-E6; NDTiff appends frames
into a couple of large files and does not pay it.

Three consequences, in increasing order of importance:

1. Users acquiring on `MMCORE_PLUS` currently get the slowest available option as
   the default.
2. **It collapses the two data shapes.** `_resolve_finished_acquisition_data()`
   and `_acquisition_storage_path()` exist in their current form only because
   `MMCORE_PLUS` has no NDTiff store while the pycromanager backends do (see
   *Acquisition storage and scratch directories* in `CLAUDE.md`). If this backend
   writes NDTiff too, both branches converge on `shared_data.mdaDatasets` and a
   whole class of backend-conditional code goes away.
3. **It may remove the scratch display store entirely.** A 0.10 ms random frame
   read is fast enough to back napari scrubbing directly. That is T-E6's step 4,
   and this measurement is the evidence it needs — which is why this task comes
   first.

**Before defaulting to NDTiff, investigate OME-TIFF and OME-Zarr properly — the
comparison above is not yet fair.** NDTiff was driven through its native API,
while both OME formats got whatever defaults `handler_for_path` picks from a bare
path string. That is a configuration comparison as much as a format comparison,
and the tell is in the file counts: `run_mda(output=…​.ome.zarr)` produced **1002
files for 1000 frames**, i.e. it fell into exactly the same one-chunk-per-frame
trap measured in T-E6 — not necessarily anything intrinsic to OME-Zarr.

This matters because the OME formats are the *interoperable* ones. NDTiff is
Micro-Manager-specific; OME-Zarr and OME-TIFF are read by anything in the imaging
ecosystem. If a properly configured OME-Zarr lands anywhere near NDTiff, it is
the better default on portability grounds alone. Decide the default on
measurements, not on format loyalty in either direction.

What to try:

- **Pass a configured writer, not a path.** `run_mda`'s `output` is typed
  `SingleOutput = Path | str | SupportsFrameReady | AcquisitionSettings`, so a
  writer *instance* is accepted. Build `OMEZarrWriter` (or its `ome-writers`
  successor) with explicit chunk and shard settings sized to the frame, rather
  than letting a bare path choose them. The T-D3/T-E6 measurements say chunking
  along the frame axis hurts *reads*, so shards over 1-frame chunks is the shape
  to test: it was the one configuration that kept a cheap random read (4.27 ms at
  1024x1024) while collapsing the file count.
- **`TensorStoreHandler`.** Also exposed by `pymmcore_plus.mda.handlers`, and
  never benchmarked here. It is the most likely candidate to be fast without
  giving up an open format.
- **The `ome-writers` path.** `pymmcore_plus.mda.handlers` emits a
  `FutureWarning` — "we are moving to ome-writers as the internally supported
  data-sink" — so the handlers benchmarked here are the *old* implementation and
  may not be what a current pymmcore-plus does at all. Measure the new sink
  before concluding anything about OME-Zarr's ceiling. `tests/test_mmcore_mda_saving.py`
  already pins that these suffixes still resolve to a handler, so that migration
  will surface as a test failure rather than silent data loss.
- **Check OME-TIFF's memory behaviour, separately from its speed.** It wrote a
  single file at 6.97 ms/frame, so its cost is *not* per-file overhead — it is
  somewhere else, and the suspicion is that it assembles the stack at
  `sequenceFinished` rather than streaming. If it buffers a whole acquisition in
  RAM that is a hard limit on long MDAs and a correctness/robustness concern, not
  a performance one. This is also why `MDA_WRITER_FINALISE_TIMEOUT_S` exists at
  300 s. Measure peak RSS across a long acquisition per format.

Record the outcome in `claude_decisions.md` whichever way it goes: "OME-Zarr was
tuned and still lost" is as useful to a future session as the reverse, and stops
this being re-litigated.

**The write path already exists in this codebase.** `MMcontrols.py` (~line 788)
constructs `NDTiffDataset(path, summary_metadata=…​, writable=True)` and calls
`put_image(coords, pixels, metadata)` / `finish()`. `napariGlados.py`'s
`PyMMCore_startedAcqCallback` (~line 1154) *already creates* the dataset as
`shared_data.pyMMCdataset` and then never writes to it — that dead store is what
this task finally makes real. `ndstorage` 0.1.18 is already a dependency.

**Files:** `glados_pycromanager/GUI/sharedFunctions.py` (the setting),
`glados_pycromanager/GUI/napariGlados.py` (the acquisition branch),
`glados_pycromanager/Core/MDAGlados.py` (storage-path / data resolution)

**Find:** `mmcore_save_format` in `MDAConfig`, `mmcore_output_path()` and the
`run_mda(...)` call in `run_MILCoreAcquisition_worker`, `PyMMCore_startedAcqCallback`.

**Do:**

1. Add `ndtiff` to `mmcore_save_format`. Unlike the other options it is **not** a
   `run_mda(output=…)` path — pymmcore-plus' `handler_for_path` only infers
   writers for `.zarr` / `.tiff` / an image-sequence directory — so it is written
   by Glados from the frame path, via the existing `pyMMCdataset` object.
2. Write it off the frame path, **not** the acquisition thread: reuse
   `ZarrFrameWriter`'s shape (bounded-by-bytes queue, backpressure, drain on
   close) rather than calling `put_image` inline. Generalise the writer over
   "something with a per-frame write" rather than duplicating it; `submit`'s
   `slice_tuple` becomes NDTiff's coordinate dict.
3. `finish()` the dataset at acquisition end, before anything reads it — the same
   ordering constraint `_stop_zarr_writer()` already has, and the reason
   `pyMMCdataset.finish()` currently logs at DEBUG is that it was never written
   to (see the resolved item in `claude_issues.md`).
4. Point `shared_data.mdaSavedPath` and `mdaDatasets` at it so
   `_acquisition_storage_path()` and `_resolve_finished_acquisition_data()`
   report it, then simplify those two now that both backends can produce the same
   shape.
5. **Re-run the benchmark before choosing the default**, on more than one frame
   size and with a cold page cache, and against *tuned* OME writers per the
   investigation note above — not the bare-path defaults. If NDTiff still wins by
   a wide margin, make it the default and say so in the setting's description; if
   a configured OME-Zarr is close, prefer it for interoperability. Either way
   record the result in `claude_decisions.md`.

**Don't:** Don't remove the OME-Zarr/OME-TIFF options — they are the
interoperable, non-Micro-Manager-specific formats and somebody will want them;
this is about the default and about having the fast option available at all.
Don't write NDTiff inline on the frame path (see 2). Don't treat the numbers
above as settled: one machine, one frame size, warm cache, and the NDTiff read
figure excludes the index-loading cost paid when *opening* a large dataset, which
was visible as a progress bar in the benchmark and needs its own measurement
before scrubbing is built on it.

**Verify:** `pytest -q`. Then a demo-camera MDA per format (the pattern in
`tests/test_mmcore_mda_saving.py`) asserting the data lands, reads back at the
acquisition's shape, and that `frameReady` still fires for every frame. Plus the
re-run benchmark from step 5.

**Commit:** `feat(storage): write pymmcore-plus MDAs as NDTiff`

---

### T-E1 — Batch per-dimension set_current_step calls

Tier: E | Depends on: none | Risk: medium | Size: M

**Why:** `napariViewer.dims.set_current_step` is called **once per dimension per frame**,
and each call triggers a full re-slice: zarr chunk fetch, zstd decompress, contrast
rescan, GPU upload. For a 4-D plan that is four complete re-slices per displayed frame.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** in `_napariUpdateLive_locked`, the `multiDstack` branch loop calling
`set_current_step` (approx. lines 381-384).

**Do:** Set all dimension steps in one update. Use napari's event blocker around the loop
followed by a single refresh, or assign `viewer.dims.current_step` as a whole tuple.
Verify against the pinned napari version which API actually coalesces — measure, do not
assume.

**Don't:** Don't suppress the final refresh; the display must still update.

**Verify:** `pytest -q`. Then an MDA with 3+ dimensions: confirm the sliders track
correctly and the frame rate improves.

**Commit:** `perf(napari): batch dimension updates into a single re-slice per frame`

---

### T-E2 — Throttle auto-contrast on the multiDstack path

Tier: E | Depends on: none | Risk: low | Size: S

**Why:** The multiDstack branch sets `layer._keep_auto_contrast = True`, so napari runs
`reset_contrast_limits()` — a full min/max scan of the freshly decompressed slice — on
**every** re-slice. The `frameByFrame` branch already solved this with
`_keep_auto_contrast = False` plus a throttled `_maybe_refresh_contrast`.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** `layer._keep_auto_contrast = True` in the multiDstack branch (approx. line 341)
and `def _maybe_refresh_contrast` (line 104).

**Do:** Use the same `_keep_auto_contrast = False` plus `_maybe_refresh_contrast` pattern
on the multiDstack path.

**Don't:** Don't change the default `contrast_refresh_every_n_frames` (10).

**Verify:** `pytest -q`. Then an MDA with `multiDstack`: brightness should still adapt,
within roughly 10 frames, and the frame rate should improve.

**Commit:** `perf(napari): throttle auto-contrast on the multiDstack path`

---

### T-E3 — Stop per-frame layer teardown/rebuild

Tier: E | Depends on: none | Risk: medium | Size: M

**Why:** The per-frame update re-derives dimensions and, on any mismatch, pops the layer
and nulls the zarr — a full teardown and rebuild including a complete texture re-upload,
from inside the hot path.

**Files:** `glados_pycromanager/GUI/napariGlados.py`

**Find:** in `_napariUpdateLive_locked`, the layer-shape validation block (approx. lines
264-306) including the `layers.pop` and the zarr reset.

**Do:** Move the shape check to acquisition start (where the plan's dimensions are already
known) rather than per frame. If a genuine mid-acquisition mismatch is possible, keep a
guarded check but make it cheap — compare a cached shape tuple, and only rebuild on an
actual change.

**Don't:** Don't remove the correctness check entirely; a mismatched layer must not be
written into.

**Verify:** `pytest -q`. Then two different-shaped MDAs back-to-back: the second must
rebuild its layer correctly. Then a long single MDA: no rebuild should occur mid-run
(log it to confirm).

**Commit:** `perf(napari): validate layer shape at acquisition start, not per frame`

---

### T-E4 — Preallocate album-mode layers

Tier: E | Depends on: none | Risk: medium | Size: M

**Why:** `addToExistingOrNewLayer` calls `np.append` to grow the stack **and then destroys
and recreates the napari layer** on every frame. `np.append` copies the entire stack each
call, so the cost is O(N^2) bytes over a run, on top of a full texture re-upload per frame.
The two-frame case also uses `np.zeros(...)` with no dtype, silently upcasting to float64.

**Files:** `glados_pycromanager/GUI/napariHelperFunctions.py`

**Find:** `def addToExistingOrNewLayer` (line 72), the `np.append` and the
`add_image` / `layers.remove` pair that follows it.

**Do:**

1. Preallocate to the known extent where one is available, and assign into the slice.
2. Mutate `layer.data` in place and call `layer.refresh()` — this is exactly the pattern
   the `frameByFrame` live path already uses correctly.
3. Pass an explicit dtype to `np.zeros` matching the incoming image.
4. Where no extent is known (true album mode, user-driven), grow geometrically (double the
   buffer) instead of appending one frame at a time, and keep a fill count.

**Don't:** Don't change the function's public signature — grep for callers first.

**Verify:** `pytest -q`. Then snap 20 images into the album and confirm all 20 are present,
in order, with the correct dtype, and that adding the 20th is not visibly slower than the
2nd.

**Commit:** `perf(napari): grow album layers in place instead of np.append plus recreate`

---

### T-E5 — Re-measure the many-layers cliff

Tier: E | Depends on: E1, E2, E3, E4 | Risk: none | Size: S

**Why:** `docs/bench-live-display.md` recorded that pre-populating the viewer with 50 dummy
layers pushed steady-state cost from approximately 13-20 ms to approximately 70-75 ms per
frame — a 4-5x regression — and left it unfixed as "napari-internals territory", while
noting that this app's RT-analysis dock is *designed* to accumulate layers over a session.

**Files:** `scripts/bench_live_display.py`, `docs/bench-live-display.md`

**Find:** the dummy-layer benchmark case in `scripts/bench_live_display.py`, and the
"candidate 2" section of `docs/bench-live-display.md` holding the original numbers.

**Do:** Re-run the existing 50-dummy-layer benchmark case after E1-E4 and append the
result. If the cliff persists, write up the mitigation options (cap or recycle RT overlay
layers; hide inactive ones) as a new entry in `claude_issues.md` — it is our problem to
mitigate even if the root cause is upstream.

**Don't:** Don't attempt a napari-internals fix in this task.

**Verify:** `make bench-live-display` runs and appends results.

**Commit:** `docs(bench): re-measure per-frame cost against total layer count`

---

### T-E6 — Take zarr off the live display path during an MDA (MMCORE_PLUS)

Tier: E | Depends on: E1-E5, F1-F5, **T-D8** (do the GUI and napari work first) | Risk: medium | Size: **L**

**Reported from a real session (2026-09-09), still open after T-E1, T-E2 and T-F3:**
during an MDA the visualisation updates only **once every 300-500 ms**, with
256x256 frames at ~5 ms frametime (~200 fps), and **only on the `MMCORE_PLUS`
backend**. The user's read is "it's really something zarr-ish".

**It is a rate problem, not a lag problem.** An earlier draft of this task
guessed the display was simply running behind the writer backlog (it follows
`writer.last_written_tag`, and 128 KB frames give a 2048-frame queue, so a
437-frame backlog would be ~2 s behind). The user checked: the view is not
seconds behind, it genuinely repaints 2-3 times a second. Do not re-run that
hypothesis.

**What the measurements say.**

The scratch display store costs about **3.2 ms per frame at 256x256**, and no
chunking arrangement improves it (1000 frames, written one at a time as the
writer thread does, uncompressed):

| frame | chunks | shards | files | ms/frame | MB/s | 1-slice read |
|---|---|---|---|---|---|---|
| 256x256 | 1 | – | 1001 | **3.19** | 41 | 0.85 ms |
| 256x256 | 32 | – | 33 | 18.09 | 7 | 3.75 ms |
| 256x256 | 1 | 32 | 33 | 21.33 | 6 | 4.49 ms |
| 1024x1024 | 1 | – | 1001 | 22.45 | 93 | 7.22 ms |
| 1024x1024 | 32 | – | 33 | 313.22 | 7 | 114.38 ms |
| 1024x1024 | 1 | 32 | 33 | 232.66 | 9 | 7.48 ms |

Two things follow. First, **the T-D3 decision to keep one frame per chunk still
holds at small frames** — this was the open worry that it had only been measured
at 1024x1024, and the answer is that multi-frame chunks are 5-6x *worse* at
256x256 too. There is nothing to win by tuning zarr here. Second, 41 MB/s for
128 KB frames is nowhere near disk bandwidth: the cost is **per-file overhead**,
one file created per frame. At a 5 ms frametime the writer therefore needs
~64% of the frame budget just to keep up, doing ~200 file creations per second
while holding the GIL for much of that. That matches the user's log — 1000
frames took 5 s to drain (09:12:09 to 09:12:14), i.e. 5 ms/frame under real
load. A writer thread that busy is a strong candidate for starving the GUI
thread, and it is the one thing that exists **only** on `MMCORE_PLUS`, which is
exactly the backend where the symptom appears.

**The bigger realisation: since the MDA now saves properly, the scratch store may
be pure overhead.** `run_mda(output=...)` writes the real archive (OME-Zarr or
OME-TIFF) to the user's Storage folder. The scratch zarr is now a *second*
complete copy of every frame, written to disk at ~3.2 ms/frame, whose only job
is to back a napari layer. Question that before optimising it.

**Files:** `glados_pycromanager/GUI/napariGlados.py`,
`glados_pycromanager/GUI/frame_writer.py`

**The design the user asked for.** During acquisition, show the newest frame the
way live mode does — straight from memory, no store round trip — **but keep the
dimension sliders moving** so the user can see where the acquisition is. Only
when the user actually starts scrubbing does the view switch to reading slices
out of the store.

**Do:**

1. Reproduce and measure first: 256x256, ~5 ms exposure, `multiDstack`,
   `MMCORE_PLUS`. Record the displayed frame rate, GUI-thread time per displayed
   frame, and the same run with the zarr writer disabled entirely — that last
   one settles whether the writer thread is what starves the GUI.
2. Two layers rather than one, which is what makes "live view + working slider"
   possible at all:
   - the existing zarr-backed stack layer, which owns the dimensions and the
     sliders, **hidden during acquisition**;
   - a plain 2-D layer on top, updated in place from the frame already in memory
     on the frame-ring consumer, exactly as the `frameByFrame` path does.
   Move the sliders on the stack layer for position feedback while it is hidden.
   **Verify that napari does not slice an invisible layer** — the whole saving
   depends on it, so measure rather than assume; if it does slice regardless,
   fall back to leaving the stack layer out of the viewer until it is needed.
3. Switch on user interaction: when a `dims` change comes from the user rather
   than from our own `set_current_step`, reveal the stack layer and hide the
   2-D overlay. Guard our own programmatic slider moves with a flag so they are
   not mistaken for scrubbing.
4. Reconsider whether the scratch store needs to be written during acquisition
   at all now that the backend writes the archive. If scrubbing could read from
   the acquisition's own store, the scratch store, its writer thread and its
   ~3.2 ms/frame disappear together. This is the largest possible win and should
   be evaluated before building 2 and 3. **T-D8 is the evidence for this**: NDTiff
   reads a random frame in ~0.10 ms against the scratch zarr's ~3.4 ms, which is
   comfortably fast enough to back scrubbing directly. Do T-D8 first; it may
   shrink this task to just the two-layer display work, or remove the need for
   it.

**Don't:** Don't reintroduce black frames — whatever replaces
`_slice_safe_to_display()` must never point the viewer at an unwritten slice;
that regression is why it exists. Don't make the storage path lossy to make the
display faster; T-D3 separated them deliberately. Don't revisit chunking or
sharding — measured above, twice, at both frame sizes.

**Verify:** `pytest -q`, plus the reproduction above showing the display
repainting at the configured fps with the camera at ~200 fps. The pymmcore-plus
demo camera makes this measurable without hardware (see
`tests/test_mmcore_mda_saving.py` for the pattern).

**Commit:** `perf(napari): display MDA frames from memory, read the store only when scrubbing`

---

### T-F1 — Memoize findIconFolder and cache pixmaps

Tier: F | Depends on: none | Risk: low | Size: M

**Why:** `findIconFolder()` runs `importlib.util.find_spec("glados_pycromanager")` plus up
to three `os.path.exists()` calls and is **never cached**. `setWarningErrorInfoIcon()` does
a `QPixmap(path)` disk read and PNG decode, `toImage()`, a **numpy grayscale conversion
over the whole image**, a `QImage` rebuild, and a smooth rescale. Together they are called
3-4 times per warning update — which the nodz timer triggers roughly twice a second — plus
once per node created.

**Files:** `glados_pycromanager/ui/widgets/builders.py`

**Find:** `def findIconFolder` (line 24) and `def setWarningErrorInfoIcon` (line 51).

**Do:**

1. Memoize `findIconFolder()` with `functools.lru_cache` (it is a pure lookup of a path
   that cannot change during a session).
2. Add a module-level cache keyed by `(icon name, alteration, size)` holding ready-to-use
   `QPixmap`s, so the grayscale conversion and rescale happen once per variant per session
   rather than per call.
3. Guard the cache against being populated before a `QApplication` exists (constructing a
   `QPixmap` without one is invalid) — populate lazily on first use, not at import.

**Don't:** Don't change the function signatures; grep shows several call sites.

**Verify:** `pytest -q`. Then launch the app and confirm warning/error icons still render
correctly in all three states (warning, error, info) and both alterations.

**Commit:** `perf(gui): memoize icon folder lookup and cache rendered pixmaps`

---

### T-F2 — Stop loading a PNG from disk inside NodeItem.paint()

Tier: F | Depends on: F1 | Risk: medium | Size: M

**Why:** `NodeItem.paint()` constructs a `QPixmap` **from disk on every repaint**. It also
builds two `QFontMetrics` objects per paint, re-lays-out an HTML `QTextDocument`, and —
a real bug — **mutates `self.attrs` inside `paint()`**, which is model mutation during
rendering.

**Files:** `glados_pycromanager/GUI/nodz/nodz_main.py`

**Find:** `def paint` at line 2312 (the `NodeItem` one, not the line 2939 one), the
`QPixmap(self.iconFolder + os.sep + 'node_*.png')` block at lines 2382-2390, and the
`self.attrs` mutation at approximately lines 2412-2421.

**Do:**

1. Load the four status pixmaps once into a module-level dict (reuse T-F1's cache) and
   look up by status in `paint()`.
2. Cache the `QFontMetrics` objects on the item or the class.
3. Move the `self.attrs` rebuild out of `paint()` to wherever attributes actually change.

**Don't:** Don't change the visual appearance. Don't construct `QPixmap`s at import time
(no `QApplication` yet).

**Verify:** `pytest -q`. Then open a recipe with several nodes, drag nodes around, and
confirm icons and text render identically and dragging is visibly smoother.

**Commit:** `perf(nodz): cache node status pixmaps instead of reloading them per paint`

---

### T-F3 — Tail-follow the log file instead of re-reading it

Tier: F | Depends on: none | Risk: low | Size: M

**Why:** The log widget does `open(logfile).read()` of the **entire** file plus
`setPlainText` plus `moveCursor(End)` on a 400-600 ms timer, on the GUI thread. The
logging setup uses a plain `FileHandler` with **no rotation**, so the file grows for the
whole session and this cost grows monotonically — worst exactly during long acquisitions.

**Files:** `glados_pycromanager/GUI/FlowChart_dockWidgets.py`

**Find:** `def update_log_content` (line 4839) and `self.timer.start(random.randint(400, 600))`
(line 4837).

**Do:**

1. Track the last read byte offset; on each tick seek to it, read only the delta, and
   `appendPlainText` the new lines.
2. Cap the document length (`QPlainTextEdit.setMaximumBlockCount`) so memory stays bounded.
3. Handle the file being rotated or truncated (offset beyond EOF): reset to 0 and reload.
4. Consider stopping the timer while `liveMode or mdaMode` — see T-F4 for the same idea.

**Don't:** Don't change the log format or the handler. Don't move the read to a thread in
this task; incremental reads are cheap enough on the GUI thread.

**Verify:** `pytest -q`. Then run the app for a few minutes with DEBUG logging, confirm the
widget still shows the newest lines and auto-scrolls, and that it does not slow down as the
log grows.

**Commit:** `perf(gui): tail-follow the log file instead of re-reading it every tick`

---

### T-F4 — Coalesce the nodz timer and gate it on acquisition

Tier: F | Depends on: F1 | Risk: medium | Size: M

**Why:** The 1 Hz `NodeScene` timer assigns `shared_data.warningErrorInfoInfo['Warnings']`
**twice per tick**. Each assignment goes through `Dict_Specific_WarningErrorInfo.__setitem__`,
which makes a **full dict copy** into `self.oldValue` — a value the handler does not even
take — and then calls `updateAutonousErrorWarningInfo`, which does 3-4 icon lookups, 3-4
pixmap builds, and a loop over every node. So the whole chain runs roughly twice a second,
forever, including during acquisition. No timer in the app is currently acquisition-aware.

**Files:** `glados_pycromanager/GUI/nodz/nodz_main.py`,
`glados_pycromanager/GUI/sharedFunctions.py`, `glados_pycromanager/GUI/utils.py`

**Find:** `self.timer.start(1000)` (nodz_main.py line 1633), `def regular_callAction`
(line 1638) and its two `warningErrorInfoInfo['Warnings']` assignments;
`def __setitem__` (sharedFunctions.py line 547) and its `self.oldValue = self.copy()`;
`def updateAutonousErrorWarningInfo` (utils.py line 3612).

**Do:**

1. In `regular_callAction`, build the complete warnings list locally and assign **once**.
2. In `__setitem__`, remove the `self.oldValue = self.copy()` full-dict copy if nothing
   reads `oldValue` (grep first; the handler does not take it).
3. Coalesce notifications: set a dirty flag and drain it via a single
   `QTimer.singleShot(0, ...)` so several mutations in one event-loop turn cause one
   rebuild.
4. Skip the periodic check entirely while `shared_data.liveMode or shared_data.mdaMode`.

**Don't:** Don't remove the warning/error functionality. Don't lower the timer interval as
a substitute for coalescing.

**Verify:** `pytest -q`. Then introduce a deliberate recipe error (a node with no
downstream connection), confirm the warning icon still appears promptly, then start live
mode and confirm the periodic rebuild stops.

**Commit:** `perf(gui): coalesce node warning updates and pause them during acquisition`

---

### T-F5 — Fix O(nodes x scene items) checkNodesOnErrors on mouse-move

Tier: F | Depends on: F1 | Risk: medium | Size: M

**Why:** `checkNodesOnErrors` assigns `node.errorInfo` inside a loop over all nodes, and
the `errorInfo` **setter** calls `updateAutonousErrorWarningInfo` — the full icon-rebuild
chain — on **each assignment**. Inside the same loop it also calls `evaluateGraph()`, which
iterates every item in the `QGraphicsScene`. It is wired to eight graph signals including
`signal_NodeMoved`, so **dragging a node re-runs this quadratic sweep with disk I/O on
every mouse-move event**.

**Files:** `glados_pycromanager/GUI/FlowChart_dockWidgets.py`,
`glados_pycromanager/GUI/nodz/nodz_main.py`

**Find:** `def checkNodesOnErrors` (FlowChart_dockWidgets.py line 3555); the `errorInfo`
setter (nodz_main.py line 2051); `def evaluateGraph` (nodz_main.py line 1573); the eight
signal connections (FlowChart_dockWidgets.py approx. lines 1733-1740).

**Do:**

1. In the loop, assign to the private `node._errorInfo` directly, then call the refresh
   **once** after the loop.
2. Hoist `evaluateGraph()` out of the per-node loop — call it once.
3. Debounce the eight signal connections through a single coalescing timer (roughly
   100 ms), so a drag produces one check at the end rather than one per mouse-move.

**Don't:** Don't remove the error checking. Don't bypass the setter in code paths outside
this loop that legitimately need the refresh.

**Verify:** `pytest -q`. Then load a recipe with 10+ nodes, drag a node across the canvas,
and confirm dragging is smooth and error icons still update correctly once the drag ends.

**Commit:** `perf(nodz): batch node error checks instead of rebuilding icons per node`

---

### T-F6 — Debounce resize rebuilds and fix the QScrollArea leak

Tier: F | Depends on: none | Risk: medium | Size: M

**Why:** `GladosWidget.resizeEvent` calls `set_groupBoxLayout`, which removes every widget
from the layout, `setParent(None)`s them, constructs a **brand-new `QScrollArea` plus
container plus `QGridLayout`**, re-adds everything, and forces a full layout pass via
`minimumSizeHint()`. This runs on **every** `QResizeEvent` — i.e. every pixel of a splitter
drag. The previous `QScrollArea` is orphaned and never `deleteLater()`d, so each resize
event leaks one.

**Files:** `glados_pycromanager/_dock_widget.py`

**Find:** `def resizeEvent` (line 88) and `def set_groupBoxLayout` (line 114). Note there
are several other `resizeEvent` overrides in this file (lines 219, 252, 280, 309, 345) —
check each for the same pattern.

**Do:**

1. Debounce: on resize, restart a roughly 150-200 ms single-shot `QTimer` and do the
   relayout only when it fires.
2. Call `deleteLater()` on the replaced `QScrollArea` and container.
3. Better: reposition the existing widgets within the existing grid layout instead of
   rebuilding the scroll area at all. Do this if it can be done safely; otherwise the
   debounce plus `deleteLater()` is an acceptable first step — note the choice in
   `claude_decisions.md`.

**Don't:** Don't change the resulting layout geometry.

**Verify:** `pytest -q`. Then drag a dock splitter slowly back and forth for 10 seconds and
confirm the layout still reflows correctly, the UI stays responsive, and memory does not
climb (watch the process in Task Manager).

**Commit:** `perf(gui): debounce dock relayout and release the replaced scroll area`

---

### T-F7 — Remove the synthetic resize and processEvents

Tier: F | Depends on: none | Risk: medium | Size: S

**Why:** `updateGUIwidgets` tears down and rebuilds seven group boxes, then **synthesises a
`QEvent.Resize` and sends it**, then calls `QCoreApplication.processEvents()`. Pumping the
event loop from inside a widget-tree rebuild allows re-entrant delivery of
`showOptionChanged` and `currentTextChanged` straight back into `updateGUIwidgets`, and can
run `napariUpdateLive` slots mid-rebuild. It also constructs a **new `QPushButton("Acquire")`
on every call**, leaking the previous one's connections.

**Files:** `glados_pycromanager/Core/MDAGlados.py`

**Find:** `def updateGUIwidgets` (line 1159); the `QApplication.sendEvent(...)` with a
constructed resize event and the `QCoreApplication.processEvents()` near the end (approx.
lines 1273-1281); the `QPushButton("Acquire")` construction (approx. line 1205).

**Do:**

1. Delete the synthetic resize event and the `processEvents()` call. If a deferred
   relayout is genuinely needed, use `QTimer.singleShot(0, ...)`.
2. Create the Acquire button once and reuse it, rather than constructing a new one per
   call.

**Don't:** Don't remove the `self.gui.update()` call. If deleting `processEvents()` visibly
breaks the layout, replace it with the `singleShot` form rather than restoring it, and note
this in `claude_decisions.md`.

**Verify:** `pytest -q`. Then toggle each of the six MDA show/hide checkboxes several times
and confirm the layout updates correctly each time and the Acquire button still works.

**Commit:** `fix(mda): remove re-entrant processEvents from the GUI rebuild path`

---

### T-F8 — textChanged to editingFinished plus debounce

Tier: F | Depends on: none | Risk: **high for the laser half** | Size: M

**The `LaserControlScripts.py` half is a decision — ask the user before changing laser
control behaviour.**

**Why:** Several controls perform hardware operations per keystroke or per slider pixel.
In `LaserControlScripts.py`, `ChangeIntensityLaserEditField` is wired to `textChanged`, so
a laser-power **serial write** happens per keystroke; `drawplot()` is wired to `textChanged`
on 15 line edits and rebuilds roughly 100 pyqtgraph items each time; `ResetLasersTrigger`
issues approximately 100+ serial round-trips in one button click; and `blinkUV` calls
`time.sleep(duration/1000)` on the GUI thread. In `MMcontrols.py`, `on_sliderChanged` does
three getters plus a `set_property` per slider pixel, and a mouse-wheel notch over the
z-stage widget triggers a **stage move**.

**Files:** `glados_pycromanager/GUI/MMcontrols.py`,
`glados_pycromanager/GUI/LaserControlScripts.py`

**Find:** in `MMcontrols.py`, `def on_sliderChanged` (approx. line 2147),
`def onEditFieldChanged` (approx. line 2192) and the wheel handler `def eventFilter`
(approx. line 1815). In `LaserControlScripts.py`, the `textChanged` connections (approx.
lines 489-504) and `def ChangeIntensityLaserEditField`.

**Do:**

1. **MMcontrols half (do this first, lower risk):** switch value-committing edits from
   `textChanged` to `editingFinished`; debounce `on_sliderChanged` so the hardware write
   happens on release or after a short idle rather than per pixel; throttle the
   wheel-over-stage handler.
2. **Laser half (ask first):** switch `ChangeIntensityLaserEditField` and the `drawplot`
   triggers to `editingFinished` plus a roughly 200 ms debounce.

**Don't:** Don't change what the controls do, only when they fire. Don't touch `blinkUV`'s
GUI-thread sleep here — that needs T-B3/T-B4 to fix properly.

**Verify:** `pytest -q`. Then, with hardware: type a new exposure and confirm it applies on
commit; drag a property slider and confirm the device reaches the final value and the UI
stays responsive.

**Commit:** `perf(gui): commit hardware edits on editingFinished instead of per keystroke`

---

### T-F9 — NapariBridge for worker-to-GUI layer updates

Tier: F | Depends on: none | Risk: **high** | Size: **L (architectural)**

**Why:** This is invariant 3, and the mirror image of the GUI-thread problem. Several
non-GUI threads mutate napari objects directly: `executor.py` iterates `napariViewer.layers`
and calls `layers.remove()` / `add_points()` / `add_shapes()` / `add_image()` from a
`QRunnable` on the thread pool; `utils.forceReset` sets `shared_data.liveMode` from a
`ThreadPoolExecutor` thread, which re-enters `acqModeChanged` and reaches
`moveLayerToTop`; and `acqModeChanged` itself runs on the acquisition worker's own thread.
This is the classic source of "layer list is inconsistent" errors and vispy segfaults.

**Files:** new `glados_pycromanager/GUI/napari_bridge.py`;
`glados_pycromanager/autonomous/executor.py`; `glados_pycromanager/GUI/utils.py`;
`glados_pycromanager/GUI/napariGlados.py`; `glados_pycromanager/GUI/AnalysisClass.py`

**Find:** the napari mutations in `executor.py` (approx. lines 463-500 and 592-629);
`def forceReset_actual` (utils.py line 3288); `def acqModeChanged` (napariGlados.py line
1053) and its `moveLayerToTop` calls. The template that already does this correctly is
`AnalysisClass.py` lines 292/315/336 — a `pyqtSignal(object)` emitted from the worker and
auto-queued to `_visualise_on_main_thread`.

**Do:**

1. Add a `NapariBridge` `QObject` constructed on and owned by the GUI thread, exposing
   slots: `add_layer`, `update_layer`, `remove_layer`, `move_to_top`, `set_dims_step`.
2. Give it signals that workers emit; rely on Qt's automatic queued connection across
   threads.
3. Migrate the call sites above to emit instead of mutating directly.
4. Where a worker currently needs the result of a layer operation, restructure so it does
   not — or provide an explicit blocking helper that is used only from non-GUI threads.

**Don't:** Don't change `AnalysisClass.py`'s existing correct pattern beyond routing it
through the bridge if that is natural. Don't introduce a synchronous wait from the GUI
thread onto a worker.

**Verify:** `pytest -q`. Then run a full autonomous recipe that adds and removes layers,
plus a Force-reset while live mode is running, and confirm no crashes, no lost layers, and
no Qt thread-affinity warnings in the log.

**Commit:** `refactor(gui): route worker napari updates through a GUI-thread bridge`

---

### T-F10 — Make the live/MDA toggle non-blocking

Tier: F | Depends on: none | Risk: medium | Size: M

**Why:** `shared_data.liveMode = X` from a button slot blocks the GUI thread: the setter
sleeps 0.1 s on the caller's thread, and `acqModeChanged`'s start path now additionally
waits up to **10 seconds** on `_worker_stopped_event` (added in `cd01032`). A single button
click can therefore freeze the UI for up to 10 s.

**Files:** `glados_pycromanager/GUI/sharedFunctions.py`,
`glados_pycromanager/GUI/napariGlados.py`, `glados_pycromanager/GUI/MMcontrols.py`

**Find:** `def on_liveMode_value_change` (sharedFunctions.py line 411) and
`def on_mdaMode_value_change` (line 426), each containing `time.sleep(0.1)`;
`def acqModeChanged` (napariGlados.py line 1053) and the
`self._worker_stopped_event.wait(timeout=self.ACQ_STOP_TIMEOUT_S)` call.

**Do:**

1. **The 10 s wait is the urgent part.** Move the wait off the GUI thread: disable the
   Live/MDA button, do the stop-then-start transition on a worker, and re-enable the button
   from a signal when the transition completes or times out.
2. **The two `time.sleep(0.1)` calls need confirmation first.** They were explicitly
   excluded at the user's request on 2026-05-20 — see `claude_decisions.md`, item H2:
   *"H2 has a subtle race condition if callers expect synchronous mode change."* Ask before
   removing them, and if you do remove them, verify every caller that assumes the mode
   change has taken effect on return.

**Don't:** Don't remove the `_acq_transition_lock` or the stop-before-start serialization —
they exist because concurrent workers caused a JVM fatal crash. Only move the *waiting* off
the GUI thread.

**Verify:** `pytest -q`. Then toggle Live on and off rapidly ten times and confirm: the UI
never freezes, the button disables during the transition, and no crash occurs. This is the
same stress case as T-B1's.

**Commit:** `ux(gui): make the live/MDA toggle non-blocking on the GUI thread`

---

### T-G1 — Cache __function_metadata__() on the registry

Tier: G | Depends on: none | Risk: medium | Size: M

**Why:** `__function_metadata__()` is never cached anywhere. Every node module rebuilds a
fresh nested dict literal on each call, and each call is followed by something far more
expensive: the metadata is **serialised into a `"key: value\n"` text blob and then parsed
back out with `re.findall`** — a serialisation layer that exists only to be immediately
deserialised. This happens 2 times per frame for `run` and 4 times per frame for
`visualise`.

**Files:** `glados_pycromanager/autonomous/registry.py`,
`glados_pycromanager/GUI/utils.py`

**Find:** `def register` (registry.py line 44) and `_REGISTRY` (line 41); in `utils.py`,
`kwargsFromFunction`, `reqKwargsFromFunction`, `optKwargsFromFunction`, `inputFromFunction`
and the blob-plus-regex code they share.

**Do:**

1. Add a metadata cache to the registry: either an optional `metadata=` argument on
   `@register`, or an `lru_cache`d `registry.get_metadata(name)` that calls
   `__function_metadata__()` once per node.
2. Rewrite the four `*FromFunction` helpers to read the cached dict **directly** instead of
   building and regexing a text blob.
3. Replace the reflection `eval`s that exist only to fetch metadata:
   `eval(f"{...}.__function_metadata__()")` in `executor.py` (two sites) and `utils.py`
   (one site).

**Don't:** Don't change the shape of the metadata dict — many call sites read it. Don't
cache across `reload_all_node_modules()`; clear the cache there (it already clears
`_REGISTRY` and the resolve cache).

**Verify:** `pytest -q`. Then open the RT-analysis dropdown and a Nodz node's parameter
panel and confirm all kwargs still render with the right widget types and defaults. Use
"Reload Glados Custom Nodes" and confirm changes to a node file are picked up.

**Commit:** `perf(registry): cache node metadata instead of re-deriving it per call`

---

### T-G2 — Coerce kwarg values at bind time

Tier: G | Depends on: G1 | Risk: medium | Size: M

**Why:** Metadata already declares `"type": float` for each kwarg, but that type is used
**only to choose a widget class**. The value itself travels as a string, is re-quoted into
a Python string literal on every frame, and is then re-parsed inside the node body
(`float(kwargs.get(...))`, `str(...).lower() in ('true','1')`).

**Files:** `glados_pycromanager/GUI/utils.py`

**Find:** `def getFunctionEvalTextFromCurrentData_RTAnalysis_run` (line 2354) and the
`name="value"` string construction it performs.

**Do:** Coerce each kwarg once, at bind time, using the metadata `"type"`, and pass typed
values through. Keep a permissive fallback: if coercion fails, pass the original string and
log a warning, so no existing recipe breaks.

**Don't:** Note the documented gap in `glados_pycromanager/Documentation/rt_analysis_parameters.md`
section 4: **for optional kwargs the Value/Variable/Advanced mode is ignored entirely** and
the raw widget text is always quoted as a string literal. Do not silently change that
behaviour here — either preserve it or fix it deliberately and update that document.
Read that file before starting.

**Verify:** `pytest -q`. Then run each RT-analysis node once and confirm its parameters take
effect (e.g. change the FFT window taper strength and see the display change).

**Commit:** `refactor(rt-analysis): coerce node kwargs once using declared metadata types`

---

### T-G3 — Resolve Variable kwargs to closures

Tier: G | Depends on: G1 | Risk: medium | Size: M

**Why:** Variable-typed kwargs are emitted as the source text
`"nodeDict['X'].variablesNodz['y']['data']"`, which is why `eval()` needs a live local
frame containing `nodeDict` — and therefore why `createNodeDictFromNodes` is rebuilt on
every frame even though its result is never otherwise used in `realTimeAnalysis_run`.

**Files:** `glados_pycromanager/GUI/utils.py`

**Find:** the Variable-kwarg branch in `getFunctionEvalTextFromCurrentData_RTAnalysis_run`
(approx. lines 2650-2654), and `def createNodeDictFromNodes` (line 3271).

**Do:** At bind time, capture a closure (e.g. `lambda node=node: node.variablesNodz['y']['data']`)
instead of emitting source text. Call it at run time to get the current value. This removes
the last reason `eval` needs a live frame and removes `createNodeDictFromNodes` from the
per-frame path.

**Don't:** Don't capture the *value* at bind time — Variable kwargs must stay live. Don't
break the Advanced (`{name@Origin}`) syntax; read
`glados_pycromanager/Documentation/rt_analysis_parameters.md` first.

**Verify:** `pytest -q`. Then build a recipe where an RT node reads a variable from another
node, change that variable mid-run, and confirm the RT node sees the new value.

**Commit:** `refactor(rt-analysis): bind Variable kwargs to closures instead of source text`

---

### T-G4 — BoundNode; delete the three per-frame eval() sites

Tier: G | Depends on: G1, G2, G3 | Risk: **high** | Size: **L (architectural)**

**Why:** `realTimeAnalysis_run` rebuilds a Python call expression from the kwarg dict and
`eval()`s it **on every analysed frame** — approximately 13 microseconds just to
`compile()`, plus approximately 8 microseconds of metadata re-derivation, plus
approximately 6 microseconds of `currentData` scanning with per-key `split('#')` and
`replace('\\','/')`. None of it can change while the analysis is running. The same shape
exists in `realTimeAnalysis_end` and `realTimeAnalysis_visualisation` — and the visualise
one runs **on the GUI thread**.

**Files:** `glados_pycromanager/GUI/utils.py`, `glados_pycromanager/GUI/AnalysisClass.py`

**Find:** `def realTimeAnalysis_init` (line 2698), `def realTimeAnalysis_run` (line 2725),
`def realTimeAnalysis_end` (line 2743), `def realTimeAnalysis_visualisation` (line 2761).
Each ends in `eval("RT_analysis_object" + evalText)`.

**Do:**

1. Define a `BoundNode` dataclass (`frozen=True, slots=True`) holding the resolved `run`,
   `visualise` and `end` callables, the coerced `kwargs` dict, the Variable-kwarg closures
   from T-G3, and the cached metadata from T-G1.
2. Build it once in `realTimeAnalysis_init` and store it where the analysis thread can
   reach it.
3. Reduce the three per-frame functions to direct calls:
   `bound.run(image, metadata, shared_data, core, **bound.kwargs)`.
4. Remove `createNodeDictFromNodes` from the per-frame path.

**Don't:** Don't change node function signatures. Don't remove the `eval` fallback until
every node type is confirmed working — keep it behind a flag for one release if that is
safer, and record that in `claude_decisions.md`.

**Verify:** `pytest -q`. Then run **every** RT-analysis node at least once (FFT, pSMLM,
SharpnessValue, RT_counter, LaserAdjustment, EndAtFrame, BioImageModelZoo) and confirm each
runs, visualises, and ends correctly. This is the riskiest task in the plan; do not shorten
this check.

**Commit:** `perf(rt-analysis): bind node dispatch once instead of eval-ing per frame`

---

### T-G5 — Opt-in subprocess state snapshots

Tier: G | Depends on: none | Risk: medium | Size: M

**Why:** After every frame the subprocess worker builds
`{k: v for k, v in vars(RT_analysis_object).items() if isinstance(v, _SUBPROCESS_SNAPSHOT_TYPES)}`
and pickles it back through the result queue. For `RealTimeFFT` that means the full-size
FFT display array **and** the cached taper window cross the process boundary every frame,
on top of the actual result. This is plausibly the single largest per-frame cost in the
system.

**Files:** `glados_pycromanager/GUI/AnalysisClass.py`,
`glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/FFT_im.py`

**Find:** `_SUBPROCESS_SNAPSHOT_TYPES` (line 352) and the snapshot comprehension at
approximately lines 448-453.

**Do:**

1. Let a node declare the attributes it needs mirrored back, via a `__snapshot_attrs__`
   key in `__function_metadata__()` or a `snapshot()` method on the class.
2. Default to **no** snapshot when nothing is declared.
3. Declare on `FFT_im.RealTimeFFT` exactly what `visualise()` actually reads — check
   whether the FFT image is already delivered via `result` or the napari layer, in which
   case it does not need to travel twice.

**Don't:** Don't break `visualise()` for the subprocess path — it depends on this mirroring
today. Verify FFT specifically before and after.

**Verify:** `pytest -q`. Then run the FFT node in subprocess mode, confirm the overlay
still updates correctly, and confirm the frame rate improves.

**Commit:** `perf(rt-analysis): make subprocess state snapshots opt-in per node`

---

### T-G6 — Probe metadata picklability once

Tier: G | Depends on: none | Risk: low | Size: S

**Why:** A full `pickle.dumps(metadata)` runs every frame purely as a validity probe, and
the result is discarded. The verdict is invariant for a given backend.

**Files:** `glados_pycromanager/GUI/AnalysisClass.py`

**Find:** `pickle.dumps(metadata)` at line 769, inside `_run_loop`.

**Do:** Probe on the first frame, cache the verdict on the instance, and re-probe only if a
later frame raises. Keep the existing fallback (`metadata = {}`) and the warning log on
failure.

**Don't:** Don't remove the safety behaviour — an unpicklable metadata object must still
not crash the worker.

**Verify:** `pytest -q`. Then run a subprocess-isolated node on each available backend and
confirm metadata still reaches the node (or is safely emptied) as before.

**Commit:** `perf(rt-analysis): probe metadata picklability once instead of per frame`

---

### T-G7 — Drop the duty-cycle sleep in the subprocess proxy

Tier: G | Depends on: none | Risk: low | Size: S

**Why:** `msleep(max(1, self.sleepTimeMs, int(analysis_elapsed_ms)))` sleeps for as long as
the last analysis took, capping the sustained rate at `1/(2T)`. For the **in-process**
thread this is a deliberate GIL-fairness trade and should stay. For the **subprocess
proxy** the compute happens in another process holding no GIL here, and the proxy thread is
idle-blocked on `_out_queue.get()` — so the sleep is pure lost throughput.

**Files:** `glados_pycromanager/GUI/AnalysisClass.py`

**Find:** the `msleep` at line 803 in `AnalysisProcess_customFunction._run_loop` (the
subprocess proxy). The one at line 932 in `AnalysisThread_customFunction._run_loop` is the
in-process one.

**Do:** In the **proxy only** (line 803), change to `self.msleep(max(1, self.sleepTimeMs))`.
Add a comment explaining why the GIL rationale does not apply here.

**Don't:** Do not change line 932. Do not remove the `sleepTimeMs` floor.

**Verify:** `pytest -q`. Then run the FFT node in subprocess mode and confirm the analysis
rate roughly doubles with no UI responsiveness regression.

**Commit:** `perf(rt-analysis): remove the duty-cycle sleep from the subprocess proxy`

---

### T-G8 — Pass the dimension map as init context

Tier: G | Depends on: none | Risk: medium | Size: M

**Why:** `pSMLM.py` and `RT_counter.py` call `utils.getDimensionsFromAcqData(shared_data._mdaModeParams)`
uncached, inside `run()` — iterating all 999 live-mode events in pure Python, on every
frame, holding the GIL. `napariGlados._get_cached_dimensions` exists but is not reachable
from node code. Reading `_mdaModeParams` also triggers the lazy `to_pycromanager()`
conversion on first access.

**Files:** `glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/pSMLM.py`,
`glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/RT_counter.py`,
`glados_pycromanager/GUI/utils.py`

**Find:** `getDimensionsFromAcqData` calls at `pSMLM.py` approx. line 161 and
`RT_counter.py` approx. line 67; `def getDimensionsFromAcqData` (utils.py line 3476); and
`def _get_cached_dimensions` (napariGlados.py line 77).

**Do:**

1. Compute the dimension map once at sequence start and expose it on `shared_data` (reuse
   or generalise `_get_cached_dimensions`; note T-D5 fixes its cache key).
2. Change both nodes to read the cached map.
3. While in `pSMLM.py`: `_smlm_frames` grows unbounded for the whole session. Bound it or
   flush it periodically.

**Don't:** Don't change node output formats.

**Verify:** `pytest -q`. Then run pSMLM on a live stream for a minute: localisations still
appear correctly, frame rate improves, and memory does not grow without bound.

**Commit:** `perf(rt-analysis): pass the acquisition dimension map into nodes once`

---

### T-G9 — Fix the thread leak on RT-node stop

Tier: G | Depends on: none | Risk: medium | Size: M

**Why:** `AnalysisThread_customFunction.run()` blocks on `self._new_image.wait()` **with no
timeout**, and `stop()` sets `is_running = False` but **never sets `_new_image`** — so the
loop never wakes to re-check the flag and the QThread blocks forever. `destroy()`'s `quit()`
only exits a Qt event loop, not an overridden `run()`. The visualisation thread has the same
problem. Every start/stop cycle of an in-process RT node therefore leaks one or two blocked
threads plus their frame deques.

**Files:** `glados_pycromanager/GUI/AnalysisClass.py`

**Find:** `def run` (line 890) / `def _run_loop` (line 909) / `def stop` (line 941) for
`AnalysisThread_customFunction`; `def run` (line 325) for the visualisation thread. The
**correct** pattern is already in `AnalysisProcess_customFunction.stop()` at line 806, which
includes `self._new_image.set()  # unblock run() if it's currently waiting`.

**Do:**

1. In both `stop()` paths, set the wake event after clearing the running flag, exactly as
   the subprocess version does.
2. Add a timeout to the `wait()` calls as a belt-and-braces deadman (1 s, matching the vis
   worker's existing pattern).
3. Join with a timeout in `destroy()` and log if a thread fails to exit.

**Don't:** Don't change the analysis semantics. Coordinate with **T-A5** item 5 if that is
already done — the teardown must be called exactly once.

**Verify:** `pytest -q` plus a regression test that `stop()` causes `run()` to return.
Then start and stop an RT node ten times and confirm via the Performance Mode thread list
that the thread count returns to baseline.

**Commit:** `fix(rt-analysis): wake analysis threads on stop instead of leaking them`

---

### T-G10 — (decision) Invert the subprocess default

Tier: G | Depends on: G5, G7 | Risk: **high** | Size: L

**Do not implement without asking the user. Present the numbers from G5 and G7 first.**

**Why:** Exactly **one of seven** RT nodes opts into `__runInSubprocess__` (`FFT_im.py`).
The other six run on QThreads inside the GUI process — including `BioImageModelZoo`
(PyTorch inference) and `pSMLM` (scipy, skimage and pandas per frame). That in-process
contention is precisely why the duty-cycle cap in T-G7 exists. The original objection to
subprocess isolation was a roughly 20 s per-start cost, which the `WarmSubprocessPool` and
`_rt_subprocess_cache` already removed.

**Proposal to put to the user:** flip the default so nodes are subprocess-isolated unless
they declare an opt-out (e.g. `__needsLiveCore__`), since nodes such as `LaserAdjustment`
legitimately need direct hardware access.

**Risks to state plainly:** node Python-level state survives stop/restart differently under
the parked-worker cache; nodes touching `core` cannot be isolated; per-node memory rises;
the picklability of each node's result and metadata must be verified individually.

**Files:** `glados_pycromanager/GUI/utils.py` (the `__runInSubprocess__` default in
`realTimeAnalysis_runInSubprocess`), `glados_pycromanager/GUI/AnalysisClass.py`, and one
`__function_metadata__()` per node under
`glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/`.

**Find:** `def realTimeAnalysis_runInSubprocess` (utils.py, approx. line 2794) and the
single `"__runInSubprocess__": True` in `FFT_im.py` (approx. line 43).

**Do:** Only if approved. Invert the default in `realTimeAnalysis_runInSubprocess`, add the
`__needsLiveCore__` opt-out, then migrate **one node per commit**, verifying each node runs,
visualises and ends correctly before moving to the next.

**Don't:** Don't migrate `LaserAdjustment` or any node that calls `core.*` — those need
direct hardware access and must opt out. Don't migrate all nodes in one commit.

**Verify:** `pytest -q`. Then, per migrated node: start it, confirm the overlay updates,
stop it, restart it, and confirm no stale state carried over (the parked-worker cache
deliberately reuses warm workers keyed by config hash).

**Commit:** `perf(rt-analysis): isolate analysis nodes in subprocesses by default`

---

### T-H1 — Debounce get_MDA_events_from_GUI

Tier: H | Depends on: none | Risk: medium | Size: M

**Why:** `get_MDA_events_from_GUI` is wired to **16** `textChanged` / `currentIndexChanged`
/ `toggled` / `itemChanged` signals. `textChanged` fires per character. Each invocation
builds a full `useq.MDASequence`, calls `to_pycromanager()` (which materialises and
pydantic-validates **one dict per frame**), read-modify-writes the whole `glados_state.json`,
**and** makes a hardware `set_focus_device()` call. Typing `100000` into "Number time
points" therefore materialises 1, then 10, then 100, then 1 000, then 10 000, then 100 000
event dicts in sequence, plus six full JSON round-trips, plus six hardware calls.

**Files:** `glados_pycromanager/Core/MDAGlados.py`

**Find:** `def get_MDA_events_from_GUI` (line 1605). Grep for
`get_MDA_events_from_GUI` to find all 16 connections.

**Do:**

1. Route every connection through a single roughly 200 ms single-shot `QTimer` debounce.
2. Switch `textChanged` connections to `editingFinished` where the widget is a `QLineEdit`.
3. Debounce the `glados_state.json` write separately (or move it to `editingFinished` /
   widget close) so it is not coupled to event generation at all.

**Don't:** Don't change what the plan builds. Don't remove `autoSaveLoad`.

**Verify:** `pytest -q`. Then type a large number of time points and confirm the UI stays
responsive, the plan is correct when you press Acquire, and settings still persist across a
restart.

**Commit:** `perf(mda): debounce MDA plan rebuilds from GUI edits`

---

### T-H2 — Keep to_pycromanager() lazy until acquisition start

Tier: H | Depends on: H1 | Risk: medium | Size: M

**Why:** `useq.MDASequence` is already a lazy, generative iterable. `to_pycromanager()`
materialises the whole event list eagerly, and `run_mda()` iterates and validates it again
internally. Phase 13 already established the lazy pattern for `Shared_data._mdaModeParams`
— extend it here.

**Files:** `glados_pycromanager/Core/MDAGlados.py`

**Find:** `self.mda = to_pycromanager(self.mda_useq)` inside `get_MDA_events_from_GUI`
(approx. line 1767-1786).

**Do:** Keep `self.mda_useq` as the source of truth and defer `to_pycromanager()` until
acquisition start (or make `self.mda` a lazily-converting cached property, mirroring the
existing `_mdaModeParams` property in `sharedFunctions.py`).

**Don't:** Don't break callers that read `self.mda` — grep for them and make sure the lazy
property serves them identically.

**Verify:** `pytest -q`. Then set up a large MDA (many timepoints), confirm the GUI stays
responsive while editing, and confirm the acquisition runs with the correct event count.

**Commit:** `perf(mda): defer pycromanager event conversion until acquisition start`

---

### T-H3 — Move set_focus_device out of the keystroke path

Tier: H | Depends on: H1 | Risk: low | Size: S

**Why:** `get_MDA_events_from_GUI` calls `MILcore.set_focus_device(...)` — a hardware
call — on every keystroke in the MDA panel.

**Files:** `glados_pycromanager/Core/MDAGlados.py`

**Find:** the `set_focus_device` calls inside `get_MDA_events_from_GUI` (approx. lines 1650
and 1694).

**Do:** Move the call to acquisition start (`MDA_acq_from_GUI` / `MDA_acq_from_Node`), where
the focus device actually needs to be applied.

**Don't:** Don't drop the call entirely — the z-stack path depends on the focus device being
set before acquisition.

**Verify:** `pytest -q`. Then run a z-stack MDA and confirm the correct focus device is used
and z positions are correct.

**Commit:** `perf(mda): set the focus device at acquisition start, not per keystroke`

---

## 6. Decisions requiring the user

Ask before implementing these. Record the answer in `claude_decisions.md`.

1. **T-G10** — invert the RT-analysis subprocess default. Present measured numbers from
   T-G5 and T-G7 first.
2. **T-F8, laser half** — changing when `LaserControlScripts.py` writes to the TriggerScope
   changes hardware behaviour.
3. **T-F10, item 2** — removing the two `time.sleep(0.1)` calls in the live/MDA setters was
   explicitly declined on 2026-05-20 (`claude_decisions.md`, H2). The 10 s wait is separate
   and does not need re-approval.
4. **T-B3** — starting the `MicroscopeService` refactor.

---

## 7. Appendix: measurement

Not a gate, and the existing numbers are stale. If you want numbers:

- `make bench-live-display` works hardware-free and appends to `docs/bench-live-display.txt`.
  It is the right tool for T-E5.
- `make profile-runtime` segfaults in the sandboxed dev environment (confirmed pre-existing
  and unrelated to any of this work). On a real machine it appends a cProfile top-25 to
  `docs/perf-runtime.txt`.
- Phase 13.14 of `claude_project.md` is an unclosed verification gate for earlier
  performance work. It is not this project's responsibility, but if you have working
  hardware, running it is worthwhile.

Reference numbers already recorded in the repo: a PYCROMANAGER_JAVA bridge round trip costs
approximately 257 ms; the Java bridge is documented by Pycromanager as capped around
100 MB/s; napari renders a 2048x2048 frame in approximately 16 ms versus approximately
39 ms for bare pyqtgraph.
