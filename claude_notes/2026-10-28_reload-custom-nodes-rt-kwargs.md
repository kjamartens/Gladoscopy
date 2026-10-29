# 2026-10-28 — Reload Custom Nodes: RT-analysis kwargs not refreshed

- **Bug confirmed:** Plugins > Reload Glados Custom Nodes didn't show added or removed RT-analysis kwargs.
- **Cause 1:** `RTAnalysisPanel` (Controls dock) builds its parameter widgets once and never rebuilt on reload.
- **Cause 2:** AppData nodes are first imported by `utils.functionNamesFromDir` under their bare stem
  (`sys.modules["MyNode"]`). The reload never removed that entry, and `_resolve_node_obj` checks the bare stem
  first, so the old metadata was still returned.
- **Fix:**
  - `discovery._purge_modules_in` drops every `sys.modules` entry loaded from a node folder.
  - `discovery.add_reload_listener` (held weakly) is notified after each reload; `RTAnalysisPanel.reloadMethods()`
    uses it to rebuild, keeping the selected method and non-default values.
  - The menu handler also calls `terminate_all_rt_subprocesses` so parked or warm RT child processes don't run
    pre-reload code.
- **Tests:** 27 passed in 12.96 s (`test_plugin_discovery.py`, `test_rt_analysis_panel.py`). Nothing committed.

## Details

### Reproduction
A scratch script created a temporary AppData-style RT node with one kwarg `a`, built the panel, rewrote the node with
`a, b`, and then called `reload_all_node_modules()`.
- **Before the fix:** `reqKwargsFromFunction` still returned `['a']`, the panel still showed only `a`, and the node
  resolved to the bare-stem module `ReproNode`.
- **After the fix:** it returns `['a', 'b']`, both widgets are shown, and the node resolves to
  `...Real_Time_Analysis.appdata.ReproNode`.
- **Runtime:** ~5–7 s.

### Changes
- `glados_pycromanager/plugins/discovery.py`: adds the purge and the reload listeners; listeners are called at the
  end of `reload_all_node_modules`.
- `glados_pycromanager/GUI/rt_analysis_panel.py`:
  - The method list and parameter build moved into `_buildMethods`. It replaces the scroll area's widget and creates a
    fresh `currentData`; running methods keep their own copy in `_runs`.
  - `reloadMethods()` rebuilds from the current node metadata.
  - `_onNodesReloaded` is the listener.
- `glados_pycromanager/GUI/napariGlados.py`: the reload menu handler now flushes parked and warm RT subprocesses.
  After that, `WarmSubprocessPool.try_claim` restarts the pool itself.
- `CLAUDE.md`: adds a note under plugin discovery.

### Tests
- New tests:
  - `test_plugin_discovery.py::test_reload_replaces_bare_stem_copy_of_appdata_node`
  - `test_plugin_discovery.py::test_reload_notifies_listeners`
  - `test_rt_analysis_panel.py::test_reload_rebuilds_kwargs_and_keeps_edits`
- The new discovery tests use a fake node package (`fake_reload_pkg`) because reloading the real node tree would
  import TensorFlow. The fixture restores `registry._REGISTRY` afterwards.
- A wider run of 5 related test files took 55 s: 53 passed, 1 failed. The failure is
  `test_node_metadata_cache::test_real_nodes_still_report_their_kwargs`, caused by the user's uncommitted
  `WindowTaperStrength2` test edit in `FFT_im.py`, not by this change.

### Open items
- RT nodes already placed in a Nodz graph keep their old parameter dialogs after a reload.
- Running analyses keep their old code until they are deactivated and reactivated.
- Not yet tried in the running app.
