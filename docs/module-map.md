# Module map

One paragraph per top-level source file. Goal: fast "where do I look?"
when starting a task. Update this file whenever a module's
responsibility changes meaningfully. Vendored Nodz internals are
deliberately not enumerated — see `glados_pycromanager/GUI/nodz/`,
treated as third-party.

Read alongside `CLAUDE.md` (architecture overview), `claude_project.md`
(active optimization plan), and `docs/adr/` (long-form decisions).

## Top of the tree

- **`glados_pycromanager/__init__.py`** — package marker. Trivial.
- **`glados_pycromanager/_dock_widget.py`** — napari-plugin entry point.
  Constructs `Shared_data`, calls `pycromanager.Core()` directly
  (assumes a running Java server on port 4827), and adds four dock
  widgets (`MMConfigWidget`, `MDAWidget`, `AutonomousMicroscopyWidget`,
  `GladosSlidersWidget`), each derived from `GladosWidget`. Sibling of
  the standalone path in `GUI/GUI_napari.py`.

## `Core/` — backend abstraction

- **`Core/microscopeInterfaceLayer.py`** (~670 LOC). `MicroscopeInterfaceLayer`
  (alias `MIL`) is the abstraction over the three backends
  (`PYCROMANAGER_JAVA`, `PYCROMANAGER_PYTHON`, `MMCORE_PLUS`). Every
  call into Micro-Manager from elsewhere in the codebase should go
  through MIL. Backend choice is set once via `set_core()`.
- **`Core/MDAGlados.py`** (~1 860 LOC). Multi-dimensional acquisition
  layer; talks to MIL. Builds event lists, runs them, and emits
  signals. Pure-Python event-list construction is a good target for
  unit tests (Phase 5.7).

## `GUI/` — Qt + napari surface

- **`GUI/GUI_napari.py`**. Standalone entry (`glados` console
  scripts). Builds a `headlessGUI` for backend choice, spawns napari,
  runs `runNapariPycroManager` in a Worker/QThread. Sets
  `NAPARI_ASYNC=1` / `NAPARI_OCTREE=1` *before* importing napari.
- **`GUI/sharedFunctions.py`** (~520 LOC, after Phase 2 hygiene). Home
  of `Shared_data` — the single cross-thread state object — plus the
  `@dataclass` config groups (`MDAConfig`, `WebhookConfig`,
  `VisualisationConfig`, `MicroManagerConfig`), the `setting(...)`
  field factory, and JSON load/save (`load_config_from_json`,
  `save_config_to_json`). Phase 7 splits this into `io/appdata.py`
  + `config/`.
- **`GUI/utils.py`** (~3 860 LOC — *god-file*). Junk drawer:
  Qt widget builders, dataclass UI generation, plugin discovery
  helpers, file cleanup, WebEngine markdown rendering, and most of the
  `eval`-based metadata reflection. **Phase 7 carves it into**
  `io/appdata.py`, `ui/widgets/builders.py`, `ui/markdown_view.py`,
  `plugins/discovery.py`, `util/fs.py`.
- **`GUI/FlowChart_dockWidgets.py`** (~6 285 LOC — *god-file*). Dock
  widgets that drive the Nodz-based autonomous-microscopy graph: node
  dialogs (`nodz_*Dialog`), the `GladosNodzFlowChart_dockWidget` itself,
  the runtime executor (`fullAutonomousRunStart`, `runScoringOnly`,
  `runAcquiring`, etc.), and per-node call actions. The Slack settings
  button + `_slack_send_enabled` helper added in Phase 2 live here.
  Phase 8 splits this along Init/Score/Acquire region lines.
- **`GUI/napariGlados.py`** (~1 343 LOC). `napariHandler` plus the
  real-time visualization and analysis loop (`napariUpdateLive`, …).
  Uses `napari.qt.thread_worker` generators heavily — that is why some
  update functions live at module scope. Contains the line-97 TODO
  about a 2-second hot-path stall (Phase 13 target).
- **`GUI/napariHelperFunctions.py`**. Smaller helpers around napari
  layers and viewer events. Imported by `napariGlados.py` and by some
  analysis nodes.
- **`GUI/MMcontrols.py`** (~2 138 LOC). Micro-Manager config-group UI:
  `MMConfigUI`, `ConfigInfo`, and the stage/ROI controls. Used by both
  the standalone path and the napari-plugin path.
- **`GUI/Analysis_dockWidgets.py`**. Dock widgets for offline /
  post-hoc analysis. Smaller than the FlowChart dock; closely tied to
  `AnalysisClass.py`.
- **`GUI/AnalysisClass.py`** (~918 LOC). The analysis pipeline class
  used outside the node-graph editor — deque-based, thread-friendly.
- **`GUI/LaserControlScripts.py`** (~552 LOC). Standalone laser sliders
  dock (`GladosSlidersWidget`). Site-specific in places — see the
  `'SMIPC'`-hostname gate in `GUI_napari.py`.
- **`GUI/custom_widget_ui.py`** (~711 LOC). Generated Qt Designer code
  for the custom-widget surface. Don't hand-edit unless you also
  re-source the `.ui`.
- **`GUI/GUI.py`**. Older monolithic entry — left for reference; the
  active entry is `GUI_napari.py`. Has known mypy issues
  (`MainWindow` undefined name) that are not worth fixing if the file
  is going away.
- **`GUI/slack_settings_dialog.py`** (Phase 2). Small `QDialog` with
  three line edits (token / signing secret / channel) and an
  `apply_to_shared_data(...)` helper. Token + secret use password echo.
- **`GUI/nodz/`** — *vendored Nodz graph editor*. Treated as
  third-party; left untouched so we can re-sync upstream. Do not
  refactor, type-annotate, lint-fix, or split files here. See
  `claude_decisions.md` and ADR 0005.

## `AutonomousMicroscopy/` — node-graph executor + nodes

- **`AutonomousMicroscopy/__init__.py`** (and the three subpackage
  `__init__.py` files). Walks the source tree + the user's AppData
  folder, importing every `.py` and re-exporting its top-level
  functions. **Important quirk**: failures are silently downgraded.
  Phase 6 refactors discovery into `plugins/discovery.py` and makes
  failures visible.
- **`AutonomousMicroscopy/MainScripts/`**:
  - `Main.py` — *dev scratch* that runs analyses against hardcoded
    test TIFFs and calls `plt.show()` at module scope. Importing it
    accidentally would block. Phase 6/ARCH-7 deletes or `__main__`-gates
    it.
  - `FunctionHandling.py` — function discovery / module inspection.
  - `HelperFunctions.py` — kwarg introspection + string-building call
    helpers (`createFunctionWithKwargs`, …). The `eval()` partner for
    the run-time executor. Phase 9 replaces the eval path with a
    `dispatch(name, **kwargs)` registry.
- **`AutonomousMicroscopy/Analysis_Measurements/`** — segmentation /
  scoring nodes (StarDist, AverageImage, RandomShapes, …). Each module
  exposes top-level functions plus a `__function_metadata__()` that
  the UI reads.
- **`AutonomousMicroscopy/Real_Time_Analysis/`** — frame-by-frame
  analysis nodes (FFT, pSMLM, sharpness, BioImageModelZoo, frame
  counters, laser adjustment).
- **`AutonomousMicroscopy/CustomFunctions/`** — site-defined helpers
  (autofocus, stroboscopic lasers, example dice-roll node).

## `Documentation/`

- **`Documentation/_CreateDocumentation.py`** — generator that produces
  `Documentation/*.html` from sources. Phase 17 will switch the
  source-of-truth to markdown and treat the HTML as a build artifact.
- The `*.html`, `*.md`, and `Images/` files are user-facing docs.

## Tests, scripts, configs

- **`tests/`** — pytest suite (34 tests as of Phase 2). Pure-logic
  coverage; no hardware required. Uses fakes/mocks.
- **`scratch/`** — local exploration (`Test.py`, `test.ipynb`).
  Excluded from sdist/wheel via
  `[tool.setuptools.exclude-package-data]`.
- **`docs/`** — engineering docs: this map, ADRs (`adr/`), the bandit
  baseline, the eval inventory, the test baseline.
- **`Makefile`**, **`pyproject.toml`**, **`.github/workflows/ci.yml`**,
  **`.pre-commit-config.yaml`** — tooling. See `CONTRIBUTING.md`.
