# ADR 0003 — `Shared_data` single-object cross-thread state

* **Status**: Accepted (historical; ratified 2026-05-17)

## Context

Glados-PycroManager is a hybrid PyQt5 + napari application with three
moving parts that all need to share state:

- The Qt UI (main thread).
- The napari viewer + its async tiling.
- Background worker threads (live update loop, analysis pipelines,
  MDA acquisition).
- Autonomous-microscopy node executor (lives on its own QThread).

Globals would be the obvious anti-pattern. Singletons add ceremony.
Passing five separate objects around (core, viewer, config, state,
queues) bloats every signature.

## Decision

A single `Shared_data` instance is constructed at startup and passed
into every component that needs state. Field categories:

- **Backend**: `MILcore`, `core`, `_headless`, `backend`.
- **Live + MDA state**: `_liveMode`, `_mdaMode`, `_mdaModeParams`,
  `_mdaModeAcqData`, the various `*Queues` / `*Threads` lists.
- **Napari**: `_napariViewer`, `mdaDatasets`, `mdaZarrData`,
  `last_display_update_time`, `newestLayerName`.
- **Config** (a `Config()` dataclass tree — `mda_config`,
  `webhook_config`, `visualisation_config`, `micromanager_config`).
- **Cross-thread signals**: `mda_acq_done_signal`, `liveUpdateEvent`
  (`pyqtSignal`s) — `Shared_data` subclasses `QObject` for this.
- **Misc lists** that emit on mutation (`LoggingList`,
  `_RTAnalysisQueuesThreads`).

## Consequences

**Positive**

- One object to pass instead of five. Signatures stay clean.
- New cross-component state has an obvious home (just add a field).
- `Shared_data` can emit Qt signals for things like
  "MDA-done" / "live frame ready" without needing a separate signal
  broker.

**Negative**

- The class becomes a junk drawer if every new feature adds a field
  without thinking. The current `Shared_data` is around 50 fields.
- Mutation is unconstrained — any code with a reference can flip
  `_liveMode`. The codebase tolerates this because it's
  single-process and the threads cooperate through signals; we don't
  use locks.
- Serialization (the JSON state at AppData) only covers the `config`
  sub-tree; the rest is runtime state.

## Alternatives considered

1. **One signal-broker + many dataclasses**. Reject: more files, no
   real win — the signals already live on `Shared_data`.
2. **Dependency injection / framework**. Reject: heavyweight for a
   research tool; nobody wants Spring-flavored Python.
3. **Globals** (e.g. `import shared`). Reject: makes testing painful
   and obscures call-graph reasoning.

## Related

- `glados_pycromanager/GUI/sharedFunctions.py` — definition.
- `CLAUDE.md` — "Shared state — `GUI/sharedFunctions.py`".
- Phase 10.3 / 10.4 adds atomic write + schema validation to the
  `config` sub-tree's JSON path.
