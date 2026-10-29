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

Each of the node folders (`AutonomousMicroscopy/Analysis_Measurements`,
`Real_Time_Analysis`, `CustomFunctions`) is scanned for `.py` files,
and so is the matching per-user folder
`appdirs.user_data_dir()/Glados-PycroManager/AutonomousMicroscopy/<subfolder>/`.

*Update:* the scanning now lives in `plugins/discovery.py`
(`load_node_modules`, `user_appdata_dir_for`), called by each folder's
`__init__.py`. A module that fails to import is logged with its
traceback instead of being silently skipped, and
*Plugins → Reload Glados Custom Nodes* re-imports every node module
(`reload_all_node_modules`). Callable node functions must also be
registered with `@register("Module.Function")`
(`autonomous/registry.py`).

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
- **Opacity**: the original loader used `exec("from .X import *")`
  and silently swallowed `ModuleNotFoundError`, so bad plugins failed
  invisibly. Failures are now logged (see the update above).
- **Testability**: the module-scope walk runs at import time. Tests
  either tolerate that or monkeypatch the AppData path
  (`tests/test_plugin_discovery.py`).

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

- `SECURITY.md` — threat-model notes for plugin discovery.
- [Writing nodes](../developer/writing-nodes.md).
