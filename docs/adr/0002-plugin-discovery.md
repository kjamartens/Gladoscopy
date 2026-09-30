# ADR 0002 — Plugin discovery from source tree + user AppData

* **Status**: Accepted (historical; ratified 2026-05-17)
* **Deciders**: Project maintainer (K. Martens)

## Context

Autonomous microscopy is **node-graph**-based. Users build recipes by
wiring nodes; each node corresponds to a Python function with a
`__function_metadata__()` accessor that the UI introspects to render
the kwarg dialog.

The set of nodes that ship with the package is incomplete by design —
sites have their own custom scoring metrics, autofocus routines, laser
control schemes, etc. We need a way for users to add nodes **without
editing the source tree**.

## Decision

`Analysis_Measurements/__init__.py`,
`Real_Time_Analysis/__init__.py`, and `CustomFunctions/__init__.py`
each do two things on import:

1. `load_additional_modules` walks the folder, appends every
   non-`__init__` `.py` to `__all__`, and `from .<module> import *`s it.
2. Walks `appdirs.user_data_dir()/Glados-PycroManager/<subfolder>/`
   and imports every `.py` file via `importlib`.

A node "ships" by being discoverable via either path. Source-tree
nodes are shipped with the package; user nodes live under per-user
AppData.

## Consequences

**Positive**

- Zero source-tree edits required for site-specific extensions.
- Per-user AppData is the natural Windows/macOS/Linux home for
  user-installed content (we already use it for `glados_state.json`).
- Adding a `.py` to AppData survives a `pip install --upgrade`.

**Negative**

- **Security**: anything that can write to that AppData folder can
  execute code on next start. Documented in `SECURITY.md`.
- **Opacity**: today the loader uses `exec("from .X import *")` and
  silently swallows `ModuleNotFoundError`. Bad plugins fail invisibly.
  Phase 6 (`reliability: log plugin load failures`) and Phase 10.5
  (`validate plugin metadata`) address both halves.
- **Testability**: the module-scope walk runs at import time. Tests
  must either tolerate that or monkeypatch the AppData path. Phase 5.6
  introduces a fixture for this.

## Alternatives considered

1. **Setuptools entry points**. Reject: requires `pip install` for each
   user node — too heavyweight for a "I want to try a different
   scoring metric" workflow.
2. **Explicit manifest in AppData** (`plugins.json`). Reject:
   duplicates information already in the file system; an empty
   directory would be invalid; the manifest would have to be hand-kept
   in sync with the actual `.py` files.
3. **Sandboxed execution**. Reject: a sandboxed numpy/StarDist
   pipeline is impractical, and the threat model already trusts the
   recipe author (see `SECURITY.md`).

## Related

- `claude_project.md` — Phase 6 (refactor) + Phase 10.5 (validation).
- `SECURITY.md` — threat-model notes for plugin discovery.
- `CONTRIBUTING.md` — "Adding a new autonomous-microscopy node".
