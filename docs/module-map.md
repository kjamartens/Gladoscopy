# Module map

One line or paragraph per source module: a quick answer to "where do I look?". Update it when a
module's responsibility changes. The vendored Nodz editor (`GUI/nodz/`) is third-party and not
listed (see [ADR 0005](adr/0005-vendored-nodz.md)). `CLAUDE.md` at the repository root has the
architecture notes in depth: the threading model, the frame path, storage, and recipe execution.

## Entry points

- **`GUI/startup.py`**: what every console script (`glados`, `gladosw`, …) runs. Creates the only
  `QApplication`, shows the splash (`GUI/startup_splash.py`), runs the single-instance check
  (`GUI/single_instance.py`), then calls `GUI_napari.main()`.
- **`GUI/GUI_napari.py`**: the standalone app. Command-line options, the backend start dialog
  (`headlessGUI`, validated by `GUI/headless_validation.py`), backend start-up, the napari viewer
  and the microscope service.
- **`_dock_widget.py`**: the napari-plugin entry (`napari.yaml`). `MainWidget` connects to a
  running Micro-Manager (Java backend) and adds the Controls, Multi-D acquisition, Autonomous
  microscopy and Performance Mode docks, each a `GladosWidget`.
- **`shortcuts.py`**, **`install_check.py`**, **`win_runtime.py`**: Start Menu shortcuts, the
  "environment older than `pyproject.toml`" warning, and a Windows DLL-loading fix.

## `Core/`: the microscope

- **`microscopeInterfaceLayer.py`**: `MicroscopeInterfaceLayer` (MIL), the one interface over the
  three backends (`PYCROMANAGER_JAVA`, `PYCROMANAGER_PYTHON`, `MMCORE_PLUS`). All microscope access
  goes through it; every hardware method holds a per-instance lock.
- **`microscope_service.py`**: `MicroscopeService`, the single thread that owns the MIL, and
  `MicroscopeProxy`, which keeps MIL's synchronous API for callers on other threads.
- **`MDAGlados.py`**: the Multi-D acquisition panel and acquisition start (also used by the
  recipe's Acquisition node).

## `GUI/`: Qt and napari

- **`napariGlados.py`**: `napariHandler`, live mode and MDA display, the frame path into napari,
  the zarr display store, and the startup window layout.
- **`MMcontrols.py`**: the Controls dock (`MMConfigUI`, `ConfigInfo`): live/snap, shutter, ROI,
  configuration groups, stages, scripts.
- **`config_group_editor.py`**, **`device_property_browser.py`**: the two dialogs opened from the
  Configurations section.
- **`rt_analysis_panel.py`**: the Real-time analysis section of the Controls dock.
- **`FlowChart_dockWidgets.py`**: the Autonomous microscopy dock: the Nodz graph, the node dialogs,
  and the Decision, Scanning and Variables tabs.
- **`AnalysisClass.py`**: real-time analysis threads, the subprocess-isolated variant, and their
  visualisation threads. **`subprocess_pool.py`** pre-spawns a worker process.
- **`layer_group.py`**: multi-layer output of real-time analysis nodes.
  **`rt_history.py`** / **`rt_replay.py`**: stored results, replayed while scrolling a finished
  acquisition.
- **`frame_ring.py`**: bounded hand-off buffer from the camera callback to the consumer thread.
  **`frame_writer.py`**: writer threads for the zarr display store and NDTiff files.
- **`fast_image_layer.py`**: a napari `Image` layer with a fast path for same-shape 2-D updates.
- **`napari_bridge.py`**: runs napari changes from worker threads on the GUI thread.
- **`napariHelperFunctions.py`**: smaller napari helpers (album mode, scale bar).
- **`sharedFunctions.py`**: `Shared_data`, the state object passed everywhere, and the settings
  dataclasses (`MDAConfig`, `VisualisationConfig`, `MicroManagerConfig`, …).
- **`utils.py`**: a large module of helpers: node-metadata access, kwarg widgets and binding, the
  advanced-settings dialog, the Help box.
- **`Analysis_dockWidgets.py`**: builds the Controls, Multi-D acquisition and Autonomous docks on
  the napari-plugin path.
- **`performance_mode_widget.py`** / **`performance_report_dialog.py`**: Performance Mode
  (CPU/memory capture).
- **`slack_settings_dialog.py`**: the Slack settings dialog.
- **`window_focus.py`**: bring a Glados window to the front on Windows.

## `autonomous/`, `plugins/`, `AutonomousMicroscopy/`: recipes and nodes

- **`autonomous/executor.py`**: runs a recipe (`FlowchartExecutorMixin`): node actions, run
  lifecycle, abort.
- **`autonomous/registry.py`**: `@register("Module.Function")` and dispatch of node functions.
- **`autonomous/recipe_io.py`**, **`autonomous/types.py`**: recipe JSON load/save and data types.
- **`plugins/discovery.py`**: imports node modules from the source folders and the user's AppData
  folders, and reloads them.
- **`AutonomousMicroscopy/Analysis_Measurements/`**, **`Real_Time_Analysis/`**,
  **`CustomFunctions/`**: the shipped nodes (see [Writing nodes](developer/writing-nodes.md)).
  **`MainScripts/FunctionHandling.py`**: kwarg checking used by nodes.
- **`AutonomousMicroscopy/ExampleRecipes/`**: demo recipes and the script that generates them.
- **`AutonomousMicroscopy/exploration_nena_frc/`**: NeNA/FRC exploration, not imported by the app.

## Support packages

- **`io/appdata.py`**: per-user state (`glados_state.json`), settings load/save, temp cleanup.
- **`observability/`**: logging setup, the uncaught-exception hook, Performance Mode capture,
  Windows scheduling hints, the startup timeline.
- **`notify/slack.py`**: Slack client and message sending.
- **`ui/layout/`**: the dock layout toolkit (theme, sections, list editor, responsive grid).
  **`ui/widgets/`**: icons and the XY stage dial.
- **`docs_links.py`**: the documentation site URL used by the Help buttons.
- **`errors.py`**, **`lazy_imports.py`**: typed exceptions; lazy stand-ins for heavy imports.

## Outside the package

- **`tests/`**: the pytest suite. No hardware needed; some tests drive pymmcore-plus' demo
  camera.
- **`scripts/`**: benchmarks and profiling helpers.
- **`docs/`**: this site (`mkdocs.yml`), plus performance logs (`*.txt`) and archived planning
  documents (`plans/`), which are not published.
