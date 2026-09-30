# Error-handling audit (Phase 10.0)

Inventory feeding Phase 10 of `claude_project.md`. Two tables:

- **Table A** — every existing bare/broad `except:` site in `.py`
  source under `glados_pycromanager/`, with the exception type each one
  should narrow to and a recommended log level. `glados_pycromanager/GUI/nodz/`
  is excluded (vendored, see ADR-0005); `glados_pycromanager/Documentation/*.html`
  is excluded (generated artefact).
- **Table B** — module boundaries that currently have **no** check,
  expanded from the seed list in the plan with the exception type,
  test plan, and sub-phase that will land each one.

Counts (this branch, commit `cdf6111`, excluding `nodz_main.py`):

| Pattern                             | Sites |
|-------------------------------------|------:|
| Bare `except:`                      |   123 |
| Broad `except Exception(:|\sas)`    |    ~30 |
| **Total**                           |  ~153 |

The plan's headline "131 bare/broad" is approximate; this audit is the
authoritative number going into the sweep.

The verification gate (10.14) targets **0** bare `except:` in `.py`
source under `glados_pycromanager/` (excluding `nodz/`). Remaining broad
`except Exception:` blocks may keep a `# noqa: BLE001` if narrowing them
would erase intentional last-line-of-defence behaviour, but each
surviving block must be either logged at `error` or paired with a
documented reason.

---

## Categories used in Table A

The `cat` column tags the pattern so reviewer can scan quickly:

| Tag           | Pattern                                                                              | Default narrowed type                                | Default log |
|---------------|--------------------------------------------------------------------------------------|------------------------------------------------------|-------------|
| `CORE_CALL`   | Pycromanager / MMCore-Plus method call (Java/Python bridge)                          | `BackendError` (wrap from `(RuntimeError, OSError, ValueError, AttributeError)`) | `warning`   |
| `WIDGET_OP`   | Qt widget operation that may race with deletion / missing item                       | `(AttributeError, RuntimeError, KeyError)`           | `debug`     |
| `DICT_KEY`    | dict/list access where the key/index is user-driven and may legitimately miss        | `(KeyError, IndexError, TypeError, AttributeError)`  | `debug`     |
| `CAST`        | `int(...)`/`float(...)`/`eval(...)` on UI text — fallback to default                 | `(ValueError, TypeError)`                            | *(none)*    |
| `IMPORT_DEFER`| optional dep import inside try                                                       | `ImportError`                                        | `info`      |
| `WIN_PATH`    | hard-coded Windows AppData path that may not exist                                   | `OSError`                                            | `debug`     |
| `CONFIG_SET`  | dataclass / shared_data attribute write that may not exist on older schema           | `(AttributeError, KeyError, TypeError)`              | `debug`     |
| `THREAD_OP`   | start/stop/destroy on a Qt / threading worker                                        | `(AttributeError, RuntimeError)`                     | `warning`   |
| `JSON_LOAD`   | JSON decode of state file                                                            | `(json.JSONDecodeError, OSError, KeyError)`          | `error`     |
| `NET_IO`      | network call (e.g. Slack send)                                                       | `(requests.RequestException, slack_sdk.SlackApiError)` → wrap in `BackendError` | `warning` |
| `EVAL_TYPE`   | `eval()` of a literal-looking string to infer type — fallback to `str`               | `(SyntaxError, NameError, ValueError, TypeError)`    | *(none)*    |
| `OPT_CALL`    | optional helper call where failure is acceptable (best-effort UI update etc.)        | `(AttributeError, RuntimeError)`                     | `debug`     |
| `CV_PIPELINE` | computer-vision / ML pipeline with optional kwargs trying fallback paths             | `(TypeError, KeyError, ValueError)`                  | *(none)*    |
| `STARTUP_TRY` | first-load force-reset / best-effort cleanup that may fail in any way                | `(AttributeError, RuntimeError, OSError)`            | `debug`     |
| `RE_RAISE`    | site where the swallow is hiding a bug — narrow **and** re-raise after log           | *(per-site)*                                         | `error`     |

`log_lvl` is the level once narrowed. `RR` (in the notes column) means the
caller cannot recover; after narrowing the block must `raise` (or
`raise <TypedError>(...) from exc`) instead of falling through.

---

## Table A — bare/broad `except:` sites

### `glados_pycromanager/Core/microscopeInterfaceLayer.py` (2 bare + 1 broad)

| line | cat         | narrowed                                            | log_lvl | notes |
|-----:|-------------|-----------------------------------------------------|---------|-------|
|  102 | `CORE_CALL` | `(RuntimeError, OSError, AttributeError)`           | warning | already broad `Exception as e`; just retype + `BackendError`-wrap |
|  452 | `CORE_CALL` | `(RuntimeError, OSError, AttributeError)`           | warning | `get_xy_position` fallback to `[0,0]` — keep fallback but log |
|  483 | `CORE_CALL` | `(RuntimeError, OSError, AttributeError)`           | warning | same pattern as 452 on `get_xy_stage_position` |

### `glados_pycromanager/Core/MDAGlados.py` (11 bare + 0 broad)

| line | cat        | narrowed                                  | log_lvl | notes |
|-----:|------------|-------------------------------------------|---------|-------|
|  293 | `WIDGET_OP`| `(AttributeError, RuntimeError)`          | debug   | `newdropbox.setCurrentText` — already logs warning, swap blanket for narrow |
|  395 | `CAST`     | `(ValueError, TypeError, AttributeError)` | *(none)*| max of int-cast list, fall back to row count |
|  604 | `CAST`     | `(ValueError, TypeError)`                 | *(none)*| `float(entry)` fallback in channel parse |
|  993 | `WIDGET_OP`| `(AttributeError, RuntimeError, TypeError)`| debug  | `addLayout` may already have parent layout |
| 1005 | `WIDGET_OP`| `(AttributeError, RuntimeError)`          | debug   | `item.widget()` may have been removed |
| 1378 | `WIDGET_OP`| `(AttributeError, RuntimeError)`          | debug   | check before continuing iteration |
| 1613 | `CAST`     | `(ValueError, TypeError)`                 | *(none)*| `float(exposure)` invalid input |
| 1625 | `CAST`     | `(ValueError, TypeError)`                 | *(none)*| `int(num_time_points)` invalid input |
| 1641 | `CORE_CALL`| `(RuntimeError, OSError)`                 | warning | `set_focus_device` fallback |
| 1690 | `WIDGET_OP`| `(AttributeError, RuntimeError)`          | debug   | `getPositionsArray` on xy list widget |
| 1718 | `WIDGET_OP`| `(AttributeError, RuntimeError, KeyError)`| debug   | channel parsing from list widget |

### `glados_pycromanager/autonomous/executor.py` (3 bare + 4 broad)

| line | cat         | narrowed                                 | log_lvl | notes |
|-----:|-------------|------------------------------------------|---------|-------|
|  455 | `OPT_CALL`  | already `Exception as e` — keep, change log | warning | already logged; reclassify to `warning` |
|  585 | `OPT_CALL`  | already `Exception as e` — keep             | warning | as above |
|  941 | `DICT_KEY`  | `(KeyError, AttributeError, TypeError)`    | debug   | scoring data missing on optional connection |
|  982 | `DICT_KEY`  | `(KeyError, AttributeError, TypeError)`    | debug   | mirror of 941 path in scoring |
| 1124 | `EVAL_TYPE` | `(SyntaxError, NameError, ValueError, TypeError)` | *(none)*| `type(eval(value))` falls back to `type(value)` |
| 1177 | `RE_RAISE`  | wrap in `NodeDispatchError(...) from exc` | error   | currently swallows node-dispatch failures; turn into `RecipeError` |
| 1269 | `RE_RAISE`  | wrap in `NodeDispatchError(...) from exc` | error   | same dispatch site, scoring-stage branch |

### `glados_pycromanager/autonomous/recipe_io.py` (0 bare + 1 broad)

| line | cat        | narrowed                          | log_lvl | notes |
|-----:|------------|-----------------------------------|---------|-------|
|   55 | `JSON_LOAD`| `(json.JSONDecodeError, OSError)` | error   | this becomes the new schema-validation site in 10.6 — narrow there |

### `glados_pycromanager/io/appdata.py` (0 bare + 4 broad, already noqa)

These sites already carry `# noqa: BLE001` with a reason. Phase 10
re-reviews them in context of 10.3 / 10.4 (atomic write + schema
validation):

| line | cat        | action                                                              |
|-----:|------------|---------------------------------------------------------------------|
|   65 | `CONFIG_SET`| keep BLE001 — single-field type drift is intentional; documented |
|  124 | `CONFIG_SET`| keep BLE001                                                       |
|  126 | `CORE_CALL` | keep BLE001 — pycromanager-side `JavaRAMDataStorage` is optional |
|  137 | `JSON_LOAD` | replace with atomic-write logic in 10.4                          |

### `glados_pycromanager/plugins/discovery.py` (0 bare + 1 broad)

| line | cat         | action                                                                                  |
|-----:|-------------|-----------------------------------------------------------------------------------------|
|  109 | `NodeLoad`  | keep BLE001 but in 10.5 wrap the failure in `NodeLoadError` and log at `warning`, push to caller |

### `glados_pycromanager/GUI/sharedFunctions.py` (4 bare + 0 broad)

| line | cat       | narrowed                                          | log_lvl | notes |
|-----:|-----------|---------------------------------------------------|---------|-------|
|   69 | `THREAD_OP`| `(AttributeError, RuntimeError)`                 | warning | stopping analysis thread; already logs `debug`, raise to `warning` |
|  227 | `DICT_KEY`| `(KeyError, TypeError, AttributeError)`           | debug   | globalData key mismatch on old state files |
|  234 | `NET_IO`  | `(slack_sdk.errors.SlackApiError, requests.RequestException, ValueError)` | error | Slack client init — already logs `error`; aligns with 10.10 |
|  382 | `OPT_CALL`| `(AttributeError, ImportError, RuntimeError)`     | debug   | `updateAutonousErrorWarningInfo` may be missing — circular import guard |

### `glados_pycromanager/GUI/napariGlados.py` (4 bare + 1 broad)

| line | cat        | narrowed                                | log_lvl | notes |
|-----:|------------|-----------------------------------------|---------|-------|
|  296 | `DICT_KEY` | `(KeyError, IndexError, TypeError)`     | debug   | zarr slice not yet rendered — keep silent fallthrough |
|  417 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`| warning | live-mode image fetch |
|  507 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`| warning | analogue in MDA mode |
|  587 | `OPT_CALL` | already `Exception as e` — keep         | warning | reclassify log level only |
|  696 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`| warning | metadata fetch from acquired image |

### `glados_pycromanager/GUI/MMcontrols.py` (12 bare + 2 broad)

| line | cat        | narrowed                                | log_lvl | notes |
|-----:|------------|-----------------------------------------|---------|-------|
|  212 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`| debug   | `get_property` may not exist on every device |
|  258 | `CORE_CALL`| already `Exception as e`                | warning | retype to `(RuntimeError, OSError)` |
|  309 | `CORE_CALL`| `(RuntimeError, OSError)`               | warning | property setter |
| 1000 | `CORE_CALL`| `(RuntimeError, OSError, ValueError)`   | error   | ZoomIn — `RR`: re-raise as `BackendError` if user-initiated |
| 1014 | `CORE_CALL`| `(RuntimeError, OSError, ValueError)`   | error   | ZoomOut symmetric |
| 1034 | `CORE_CALL`| `(RuntimeError, OSError, ValueError)`   | error   | `setROI` — keep as warning, surface failure |
| 1141 | `WIDGET_OP`| `(AttributeError, RuntimeError)`        | debug   | shape callback iteration |
| 1468 | `CORE_CALL`| already `Exception as e`                | warning | retype |
| 1494 | `CORE_CALL`| `(RuntimeError, OSError)`               | debug   | optional shutter probe |
| 1602 | `CAST`     | `(ValueError, TypeError)`               | *(none)*| `float(text)` on entry |
| 1666 | `CAST`     | `(ValueError, TypeError)`               | *(none)*| as above |

### `glados_pycromanager/GUI/utils.py` (36 bare + 7 broad)

This file is the biggest cluster. Many sites are best-effort UI
fallbacks; they map to `WIDGET_OP` / `CAST` / `DICT_KEY`. A handful
(force-reset path) is `STARTUP_TRY`. Tabulated compactly:

| line | cat          | narrowed default                         | log_lvl |
|-----:|--------------|------------------------------------------|---------|
|  148 | `WIN_PATH`   | `OSError`                                | debug   |
|  621 | `DICT_KEY`   | `(KeyError, IndexError, TypeError)`      | debug   |
|  646 | `DICT_KEY`   | `(AttributeError, KeyError)`             | debug   |
|  689 | `DICT_KEY`   | `(KeyError, AttributeError)`             | debug   |
|  694 | `DICT_KEY`   | `(KeyError, AttributeError)`             | debug   |
|  730 | `DICT_KEY`   | `(KeyError, AttributeError, TypeError)`  | debug   |
|  815 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
|  820 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
|  833 | `DICT_KEY`   | `(KeyError, AttributeError)`             | debug   |
|  841 | `DICT_KEY`   | `(KeyError, AttributeError)`             | debug   |
|  844 | `DICT_KEY`   | `(KeyError, AttributeError)`             | debug   |
|  848 | `DICT_KEY`   | `(KeyError, AttributeError)`             | debug   |
| 1471 | `WIDGET_OP`  | `(AttributeError, RuntimeError, TypeError)` | debug |
| 1990 | `CAST`       | `(ValueError, TypeError)`                | *(none)*|
| 2006 | `CAST`       | `(ValueError, TypeError)`                | *(none)*|
| 2676 | `OPT_CALL`   | already broad `Exception as e`           | warning |
| 2695 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 2712 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 2832 | `OPT_CALL`   | already broad                            | warning |
| 2859 | `OPT_CALL`   | already broad                            | warning |
| 2875 | `OPT_CALL`   | already broad                            | warning |
| 3011 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3016 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3028 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3085 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3136 | `STARTUP_TRY`| `(AttributeError, RuntimeError)`         | debug   |
| 3141 | `STARTUP_TRY`| `(AttributeError, RuntimeError)`         | debug   |
| 3147 | `STARTUP_TRY`| `(AttributeError, RuntimeError, OSError)`| debug   |
| 3152 | `STARTUP_TRY`| `(AttributeError, RuntimeError, OSError)`| debug   |
| 3158 | `STARTUP_TRY`| `(AttributeError, RuntimeError, OSError)`| debug   |
| 3210 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3214 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3216 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3284 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3323 | `OPT_CALL`   | already broad                            | warning |
| 3433 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3627 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |
| 3673 | `WIDGET_OP`  | `(AttributeError, RuntimeError)`         | debug   |

Line 148 (`WIN_PATH`) is special: it hardcodes
`C:\Users\Koen Martens\AppData\Local\UniBonn\Glados`. Phase 10 leaves
this functionally alone (Phase 14/17 may relocate it) but narrows the
exception. The hard-coded path is tracked separately as a HYG follow-up.

### `glados_pycromanager/GUI/FlowChart_dockWidgets.py` (28 bare + 0 broad active)

The 6 285-LOC dock module — bulk of the sweep. Five broad sites here are
commented out (`# except:` lines 1598..1642, 2932 etc.) and are noise
from previous edits; ignore those. Live sites:

| line | cat         | narrowed default                            | log_lvl |
|-----:|-------------|---------------------------------------------|---------|
|  531 | `WIDGET_OP` | `(AttributeError, RuntimeError, KeyError)`  | debug   |
|  561 | `WIDGET_OP` | `(AttributeError, RuntimeError, KeyError)`  | debug   |
| 1142 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 1445 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 2469 | `DICT_KEY`  | `(KeyError, AttributeError, TypeError)`     | debug   |
| 2547 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 2560 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 2749 | `WIDGET_OP` | `(AttributeError, RuntimeError, KeyError)`  | debug   |
| 2756 | `DICT_KEY`  | `(KeyError, AttributeError, TypeError)`     | debug   |
| 3144 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3163 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3169 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3175 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3186 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3200 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3261 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3267 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3412 | `DICT_KEY`  | `(KeyError, AttributeError, TypeError)`     | debug   |
| 3428 | `DICT_KEY`  | `(KeyError, AttributeError, TypeError)`     | debug   |
| 3522 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3836 | `OPT_CALL`  | `(AttributeError, RuntimeError, KeyError)`  | warning |
| 3863 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 3904 | `OPT_CALL`  | `(AttributeError, RuntimeError, KeyError)`  | warning |
| 4133 | `OPT_CALL`  | `(AttributeError, RuntimeError, KeyError)`  | warning |
| 4430 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 4437 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |
| 4602 | `WIDGET_OP` | `(AttributeError, RuntimeError)`            | debug   |

### `glados_pycromanager/GUI/AnalysisClass.py` (4 bare + 0 broad)

| line | cat        | narrowed                                     | log_lvl |
|-----:|------------|----------------------------------------------|---------|
|   54 | `WIDGET_OP`| `(AttributeError, RuntimeError)`             | debug   |
|  469 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`    | warning |
|  485 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`    | warning |

(line 765 is commented out.)

### `glados_pycromanager/GUI/LaserControlScripts.py` (6 bare + 0 broad)

| line | cat        | narrowed                                     | log_lvl |
|-----:|------------|----------------------------------------------|---------|
|   48 | `OPT_CALL` | `(AttributeError, RuntimeError, ValueError)` | warning |
|  156 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`    | warning |
|  184 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`    | warning |
|  458 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`    | warning |
|  505 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`    | warning |
|  552 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`    | warning |

(LaserControlScripts.py is not in 10.2's per-file commit list — bundle
its narrow-sweep into a follow-up `reliability:` commit during 10.2 or
into 10.14's clean-up commit so the gate's grep returns zero.)

### `glados_pycromanager/GUI/Analysis_dockWidgets.py` (1 bare)

| line | cat       | narrowed                              | log_lvl |
|-----:|-----------|---------------------------------------|---------|
|  129 | `DICT_KEY`| `(KeyError, AttributeError, TypeError)`| debug   |

### `glados_pycromanager/GUI/GUI.py` (1 bare)

| line | cat          | narrowed                          | log_lvl |
|-----:|--------------|-----------------------------------|---------|
|   79 | `IMPORT_DEFER`| `ImportError`                    | info    |

### `glados_pycromanager/GUI/napariHelperFunctions.py` (1 bare)

| line | cat       | narrowed                                   | log_lvl |
|-----:|-----------|--------------------------------------------|---------|
|  182 | `WIDGET_OP`| `(AttributeError, RuntimeError, KeyError)`| debug   |

### `glados_pycromanager/GUI/_dock_widget.py` (0 bare + 1 broad)

| line | cat       | narrowed                                  | log_lvl |
|-----:|-----------|-------------------------------------------|---------|
|  367 | `CORE_CALL`| `(RuntimeError, OSError, AttributeError)`| warning |

### `glados_pycromanager/GUI/GUI_napari.py` (0 bare + 3 broad)

| line | cat         | action                                                                |
|-----:|-------------|-----------------------------------------------------------------------|
|  119 | `IMPORT_DEFER`| keep broad (3rd-party plugin); change log level to `warning`        |
|  270 | `STARTUP_TRY`| narrow to `(RuntimeError, OSError, ImportError)`; `error` log; `RR` on second attempt |
|  302 | `STARTUP_TRY`| same as 270 — the headless-fallback path                             |

### `glados_pycromanager/ui/widgets/builders.py` (0 bare + 1 broad, noqa)

| line | cat       | action                                                  |
|-----:|-----------|---------------------------------------------------------|
|   81 | `OPT_CALL`| keep BLE001 — icon-load failure should not break the UI |

### `glados_pycromanager/AutonomousMicroscopy/Analysis_Measurements/StarDist_image.py` (6 bare)

| line | cat         | narrowed                                | log_lvl |
|-----:|-------------|-----------------------------------------|---------|
|   89 | `CV_PIPELINE`| `(TypeError, KeyError, ValueError)`    | *(none)*|
|   93 | `CV_PIPELINE`| `(TypeError, KeyError, ValueError)`    | *(none)*|
|   97 | `CV_PIPELINE`| `(TypeError, KeyError, ValueError)`    | *(none)*|
|  165 | `CV_PIPELINE`| `(TypeError, KeyError, ValueError)`    | *(none)*|
|  169 | `CV_PIPELINE`| `(TypeError, KeyError, ValueError)`    | *(none)*|
|  173 | `CV_PIPELINE`| `(TypeError, KeyError, ValueError)`    | *(none)*|

This is the classic "try with both kwargs, then one, then neither"
pattern. After narrowing it is still ugly but at least
typed. **Decision opportunity**: refactor to one `**filtered_kwargs`
construction in a follow-up rather than three nested tries — defer to
Phase 12 (lazy imports) or a dedicated cleanup.

### `glados_pycromanager/AutonomousMicroscopy/Analysis_Measurements/checkAgainstList.py` (2 bare)

| line | cat       | narrowed                              | log_lvl |
|-----:|-----------|---------------------------------------|---------|
|   59 | `CAST`    | `(ValueError, TypeError)`             | *(none)*|
|   67 | `CAST`    | `(ValueError, TypeError)`             | *(none)*|

### `glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/BioImageModelZoo.py` (1 bare)

| line | cat          | narrowed                              | log_lvl |
|-----:|--------------|---------------------------------------|---------|
|  202 | `IMPORT_DEFER`| `ImportError`                        | warning |

### `glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/pSMLM.py` (1 bare)

| line | cat       | narrowed                              | log_lvl |
|-----:|-----------|---------------------------------------|---------|
|  217 | `CV_PIPELINE`| `(TypeError, ValueError, RuntimeError)`| warning |

### `glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/FFT_im.py` (0 bare + 1 broad)

| line | cat        | action                            |
|-----:|------------|-----------------------------------|
|   86 | `OPT_CALL` | already broad; keep + log warning |

---

## Table B — missing boundary checks

Each row is a sub-phase commit. "Tests" lists positive (P) and negative
(N) cases that must ship with the check.

| # | Boundary                                                | New typed exception     | Sub-phase | Tests |
|---|---------------------------------------------------------|-------------------------|-----------|-------|
| 1 | `Shared_data` JSON **load** — corrupted, missing version, future version | `ConfigError`                  | 10.3      | P1 round-trip; N1 invalid JSON; N2 missing version; N3 future-version |
| 2 | `Shared_data` JSON **write** — atomic temp + `os.replace`               | `ConfigError`                  | 10.4      | P1 normal write; N1 crash mid-write leaves prior file intact (monkeypatched `json.dump` raising halfway) |
| 3 | Plugin loader — malformed `__function_metadata__`, missing top-level callable | `NodeLoadError`         | 10.5      | P1 valid `.py` drop; N1 metadata missing; N2 metadata wrong shape; N3 duplicate registration |
| 4 | `recipe_io.load` — schema version, required region keys, dangling node IDs | `RecipeError`            | 10.6      | P1 `Showcase_Basic1.json`; N1 wrong schema version; N2 missing `Acquisition` region; N3 dangling connection target; N4 unparseable JSON |
| 5 | `MIL.set_core` — reject `None`, log once on `UNKNOWN`                  | `BackendError`                  | 10.7      | P1 each backend; N1 `None`; N2 bogus object → `UNKNOWN` |
| 6 | MDA event builder — negative frames, missing channels, zero step, mutex defaults | `MDAEventError`     | 10.8      | P1 happy path; N1 `num_time_points<0`; N2 channel name unknown; N3 z_step=0 with z_start≠z_end; N4 the mutex-defaults case currently captured by `test_default_call_raises_due_to_mutex_defaults` (claude_issues entry) — convert to expect `MDAEventError` |
| 7 | Headless dialog — MM path exists, config file exists with `.cfg` suffix, Start disabled otherwise | *(no raise; UI gating)* | 10.9      | P1 valid path; N1 nonexistent path; N2 missing `.cfg`; N3 valid path + invalid cfg |
| 8 | Slack send — empty token (info+no-op), wrap network failure              | `BackendError` (wrapping NET_IO) | 10.10     | P1 happy mocked send; N1 empty token → log info, no raise; N2 `requests` raises → `BackendError` raised |
| 9 | AppData plugin walk — missing/unreadable directory                      | *(no raise; warning log)*       | 10.11     | P1 normal walk; N1 nonexistent path; N2 PermissionError simulated via monkeypatched `os.walk` |
|10 | Registry `dispatch` — unknown name                                      | `NodeDispatchError`             | 10.12     | P1 known name; N1 `dispatch("nope")`; N2 wrong-arity call → wrapped in `NodeDispatchError` |
|11 | Global excepthook — unhandled exception lands in AppData log file        | *(no raise; observer)*          | 10.13     | P1 raise inside thread, assert log contains traceback |

The numbered list matches the seed in `claude_project.md` step 10.0,
with the MDA mutex-defaults entry from `claude_issues.md` rolled into
Table B row 6 (sub-phase 10.8) per the deferral note in the issue
inbox.

---

## How this audit will be used

For each sub-phase in 10.2 the file's rows above are the per-line
checklist; the commit must

1. apply the narrowed exception tuple,
2. set the log level per the table,
3. for `RR` rows, re-raise as the relevant typed exception from `errors.py`,
4. add a regression test if the previously-swallowed failure is
   *reachable* via the existing tests' fake MIL or via a small
   monkeypatch (not all sites — the table flags which).

10.14 grep gate: `grep -R "except:" glados_pycromanager --exclude-dir=nodz`
must return 0 against `.py` files, and `grep -R "except Exception" ...`
must show only sites carrying a `# noqa: BLE001` with a reason comment
on the same line (or the `RE_RAISE` re-raise form).
