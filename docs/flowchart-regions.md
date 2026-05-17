# `FlowChart_dockWidgets.py` — region map

`glados_pycromanager/GUI/FlowChart_dockWidgets.py` is 6 334 lines, dominated by
one ~3 650-line class (`GladosNodzFlowChart_dockWidget`). This document maps
the file's existing `#region` markers and class boundaries to the extraction
targets in Phase 8.2 – 8.5 of `claude_project.md`, so future sub-phases can
move ranges out one slice at a time without re-reading the whole file.

Line numbers are the values at the time of writing (commit `6301f9e`-ish on
`claude_optimization`). They will drift as extractions happen — the *region
identity* (region name, class name, method name) is the durable identifier;
the line numbers are only a navigation aid.

## File-level regions

| Lines        | `#region` label             | Contents (high level)                                                                                                                                |
|-------------:|------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 – 97       | `imports`                    | `sys.path` shim, PyQt5 imports, star-imports from the three autonomous-microscopy plugin packages, MIL/MDAGlados/MMcontrols/Nodz/slack-dialog imports |
| 99 – 1 302   | `Dialogs_Nodz`               | 20 `QDialog` subclasses — one per node-editing dialog (analysis, custom function, RT analysis, sticky note, slack, MM config, MDA, scoring-end, case switch, FoV-find, etc.) |
| 1 304 – 1 459 | `NodzHelperClasses`         | `CustomGraphicsView` (Qt graphics view), `GladosGraph` (graph-eval container), `NodeSignalManager` (dynamic-signal registry)                          |
| 1 461 – 5 109 | *(no file-level region)*    | `GladosNodzFlowChart_dockWidget` — the god-class (subdivided below)                                                                                  |
| 5 111 – 5 354 | `ScanningWidget`            | `ScanningWidget` + `advScanGridLayout` — XY/Z scan-planning UI                                                                                       |
| 5 356 – 5 850 | `DecisionWidget`            | `DecisionWidget` + `advDecisionGridLayout` — scoring-decision configuration UI                                                                       |
| 5 852 – 6 151 | `VariablesWidget`           | `HoverTableWidget`, `VariablesBase`, `VariablesWidget`, `VariablesDialog` — runtime-variables inspector                                              |
| 6 153 – 6 199 | `LoggerWidget`              | `LoggerWidget` (read-only tail of AppData log file)                                                                                                  |
| 6 201 – 6 305 | `NodzWorkers`               | `WorkerSignals` + `generalNodzCallActionWorker` — the `QRunnable` that actually executes node call-actions (incl. `eval(evalText)` for analysis/custom-function nodes) |
| 6 308 – 6 334 | *(no region)*               | `flowChart_dockWidgets(...)` factory — builds the dock widget for the main GUI                                                                       |

## Sub-regions inside `GladosNodzFlowChart_dockWidget`

The class declares its own intra-class `#region` markers:

| Lines        | `#region` label                       | Contents                                                                                                                                                |
|-------------:|---------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 468 – 1 800 | *(no region — `__init__` + UI wiring)* | Dock-widget construction: button row, warning icons, scanning/decision/variables/logger tabs, signal hookups, shared-data wiring, slack-settings button |
| 1 800 – 2 849 | `NodzFlowChart Node Methods`          | `defineNodeInfo`, `performPostNodeCreation_Start`, `nodeRan`, `NodeDoubleClicked`, `NodeAdded`, `NodeFullyInitialised`, `NodeRemoved`, `finishedEmits`, `giveInfoOnNode`, `singleNodeTypeInit`, `obtainAllNodes`, `updateNumberStartFinishedDataAttributes`, `advNodeInfo`, `explore_attributes`, `nodeLookupName_withoutCounter`, `findNodeByName`, `changeNodeName`, `changeNodeColor`, `limitTextLength`, `set_readable_text_after_dialogChange` — i.e. *all* CRUD on node objects |
| 2 851 – 3 625 | `NodzFlowChart Helpers`               | `getDevicesOfDeviceType`, plug/socket connection callbacks (`PlugOrSocketConnected`, `PlugConnected`, `SocketConnected`), `prepareGraph`, `GraphToSignals`, `getNodz`, `updateCoreVariables`, `createSingleCoreVar`, `cleanupNodeList`, `checkNodesOnErrors` |
| 3 627 – 3 672 | `NodzFlowChart Saving Loading`        | `storeGraphJSON`, `loadGraphJSON` — JSON recipe persistence (uses inherited `NodzMain.Nodz.saveGraph` / `loadGraph_KM`)                                 |
| 3 674 – 4 693 | `NodzFlowChart Node-specific`         | Per-node-type update + run handlers: `update_scoring_end`, `update_plugs_fromDialog`, `changeConfigStorageInNodz`, `changeRelStageStorageInNodz`, `AnalysisNode_DEBUG_started`, `AnalysisNode_started`, `analysisNode_finished`, `CustomFunctionNode_*`, `MMstageChangeRan`, `MMconfigChangeRan`, `acquiringStart/End`, `initStart/End`, `scoringStart/End`, `earlyScoringFail`, `and_logicCallAction`, `timerCallAction`, `storeDataCallAction`, `changeGlobalVarCallAction`, `newGlobalVarCallAction`, `ifStatementCallAction`, `runInlineScriptCallAction`, `runCaseSwitchCallAction`, `runslackReportCallAction` |
| 4 695 – 4 943 | `NodzFlowChart runs`                  | High-level run orchestration: `fullAutonomousRunStart`, `startNewScoreAcqAtPos`, `runInitOnly`, `runScoringOnly`, `runScoring`, `runAcquiring`, `interruptRun`, `_slack_send_enabled`, `openSlackSettingsDialog`, `debugScoring` |
| 4 945 – 5 109 | `NodzFlowChart GraphArea functions`   | `contextMenuEvent`, `createNewNode`, `createNodeFromRightClick`, `focus` — Qt graphics-view interaction |

## How this maps to Phase 8.2 – 8.5

> The targets below name *destination modules* under `glados_pycromanager/autonomous/`. The plan keeps the
> Nodz vendored folder untouched and leaves the Qt dock + Nodz glue as the residue.

### 8.2 — `glados_pycromanager/autonomous/types.py` (pure data classes / enums)

Candidates today:

- `GladosGraph` (1 333 – 1 388) — small data container around graph-eval text + nodes.
- `WorkerSignals` (6 203 – 6 207) — trivial Qt signal holder; technically Qt-bound but is data-shape only.
- *Enum / dataclass surface is otherwise sparse.* Most "types" today are dicts in `defineNodeInfo`; converting
  those to dataclasses is an opportunity but is **out of scope** for 8.2 — 8.2 only extracts what is *already*
  a discrete type. If the slice is empty after exclusion, that is a valid outcome — record in
  `claude_decisions.md` and move on.

### 8.3 — `glados_pycromanager/autonomous/recipe_io.py` (JSON recipe load/save)

- `storeGraphJSON` (3 628 – 3 639) — thin wrapper around `QFileDialog` + inherited `saveGraph`.
- `loadGraphJSON` (3 641 – 3 671) — `QFileDialog` + `clearGraph` + counter reset + `loadGraph_KM`.
- The *actual* serialization logic lives in vendored Nodz (`saveGraph`, `loadGraph_KM`). The extraction here
  is the **glue + validation layer**, not the byte-level format. Phase 10.6 will add schema validation on top.

### 8.4 — `glados_pycromanager/autonomous/executor.py` (runtime executor)

The "executor" is split across three regions today; they all move together:

- `NodzFlowChart runs` (4 695 – 4 943) — top-level orchestration (`fullAutonomousRunStart`,
  `startNewScoreAcqAtPos`, `runInitOnly`, `runScoringOnly`, `runScoring`, `runAcquiring`, `interruptRun`).
- `NodzFlowChart Node-specific` (3 674 – 4 693) — per-node-type run handlers (`*Start`, `*End`,
  `*CallAction`). These are the executor's behavior for each node type.
- `NodzWorkers` (6 201 – 6 305) — `generalNodzCallActionWorker` (`QRunnable`) is the worker the executor
  spawns; the in-worker `eval(evalText)` (line 6 300) is what Phase 9 replaces with a registry dispatch.

`prepareGraph` + `GraphToSignals` (in `NodzFlowChart Helpers`, 3 433 – 3 524) are the *graph compilation*
step that the executor invokes. They move with the executor.

Methods that *must remain* on the dock widget because they touch Qt UI / Nodz objects:
- `set_readable_text_after_dialogChange`, `changeNodeName`, `changeNodeColor`, `advNodeInfo`,
  `contextMenuEvent`, `createNewNode`, `focus`, etc.

The executor extraction strategy is to make the executor a *collaborator* of the dock widget, not a base
class — pass the dock widget (or a narrow protocol) in so per-node handlers can still call back into
`set_readable_text_after_dialogChange` etc.

### 8.5 — residue in `FlowChart_dockWidgets.py` (Qt dock + Nodz glue only)

After 8.2 – 8.4 the file should contain:

- All `Dialogs_Nodz` (1 099 – 1 302) — pure Qt dialogs, stay put unless a future phase carves them out.
- `NodzHelperClasses` (1 304 – 1 459) minus what 8.2 moved.
- `GladosNodzFlowChart_dockWidget` — only `__init__` + UI wiring, `NodzFlowChart Node Methods` (CRUD on
  node objects, still tightly coupled to Nodz internals), `NodzFlowChart Helpers` minus
  `prepareGraph`/`GraphToSignals`, `NodzFlowChart GraphArea functions`.
- `ScanningWidget`, `DecisionWidget`, `VariablesWidget`, `LoggerWidget` (5 111 – 6 199) — Qt widgets,
  stay put.
- `flowChart_dockWidgets(...)` factory (6 308 – end) — stays put.

Plan target is **< 1 500 LOC**. Rough headroom after the executor (≈ 1 250 LOC) and the recipe-I/O glue
(≈ 50 LOC) leave is realistic.

## What this map deliberately does *not* do

- It does **not** propose moving `Dialogs_Nodz` (≈ 1 200 LOC). Those are Qt dialogs tightly coupled to the
  dialog-edit flow; extracting them is a different refactor and is not on the current plan.
- It does **not** propose moving `ScanningWidget` / `DecisionWidget` / `VariablesWidget` / `LoggerWidget`.
  Same reason.
- It does **not** touch `glados_pycromanager/GUI/nodz/` — vendored, excluded by plan.

## How to use this document

When executing 8.2 – 8.5, treat the tables above as the address book:

1. Open the file at the line range listed.
2. Confirm the methods/classes named are still there (line numbers may have drifted).
3. Move the named symbols, update imports at both call sites and the new module, and run the test suite.
4. Update this document if a region split changes.
