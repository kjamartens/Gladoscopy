# RT-analysis / Analysis node parameters: metadata, widgets, and Value/Variable/Advanced

This document describes how kwargs of Analysis-measurement and Real-Time-Analysis
nodes (`AutonomousMicroscopy/Analysis_Measurements/`, `AutonomousMicroscopy/Real_Time_Analysis/`,
`AutonomousMicroscopy/CustomFunctions/`) become editable fields in the node-graph
parameter panel, and how the "Value / Variable / Advanced" switch works. Read this
before changing anything in `GUI/utils.py` related to kwarg widgets — the mechanism
is not covered by `CLAUDE.md`'s high-level architecture section and is easy to
break silently because most of the wiring is done by object-name convention
rather than by type.

## 1. Where kwargs come from: `__function_metadata__()`

Every node-providing module defines a module-level function:

```python
def __function_metadata__():
    return {
        "RealTimeFFT": {
            "required_kwargs": [],
            "optional_kwargs": [
                {"name": "LogScale", "description": "Apply log scaling to FFT", "default": True, "type": bool},
                {"name": "WindowTaper", "description": "...", "default": False, "type": bool},
                {"name": "WindowTaperStrength", "description": "...", "default": 0.25, "type": float},
            ],
            ...
        }
    }
```

**There is no `inspect.signature()`-based introspection anywhere in this pipeline.**
Kwarg names, descriptions, defaults and types come *exclusively* from this
hand-written dict. If you add a new kwarg to a node function, you must also add
it to `__function_metadata__()` or it will not appear in the GUI at all.

`"type"` is a real Python type object (`str`, `int`, `float`, `bool`), or the
sentinel string `'fileLoc'` for a file-picker field. It is read via
`typeFromKwarg()` (`GUI/utils.py`) and used for:

- choosing the Value-mode widget (`QCheckBox` for `bool`, file-picker button for
  `'fileLoc'`, `QLineEdit` otherwise) — see §3,
- cosmetic red/normal border validation while typing (`kwargValueInputChanged`),
- filtering the "Choose Var"/"Add Var" picker dialog to type-compatible variables
  (`VariablesDialog` in `GUI/FlowChart_dockWidgets.py`).

`"default"` is read via `defaultValueFromKwarg()` and used to pre-fill the widget.

## 2. The Value / Variable / Advanced switch

Every non-fileLoc kwarg gets **three** parallel input widgets plus a mode switch,
all created together (in `layout_init()`, `GUI/utils.py`) and coexisting in the
layout at all times (only visibility toggles):

| Object name | Widget | Purpose |
|---|---|---|
| `ComboBoxSwitch#<function>#<kwarg>` | `QComboBox` (`Value`/`Variable`/`Advanced`) | selects which of the three fields below is active |
| `LineEdit#<function>#<kwarg>` | `QLineEdit` (or `QCheckBox` for bool, see §3) | **Value** mode: a literal, typed-in value |
| `LineEditVariable#<function>#<kwarg>` | read-only `QLineEdit`, filled via "Choose Var" button | **Variable** mode: exactly one reference, `name@Origin` |
| `LineEditAdv#<function>#<kwarg>` | `QLineEdit`, augmented via "Add Var" button | **Advanced** mode: free text containing one or more `{name@Origin}` tokens, e.g. `{WaitTime@Global}+1` |

`Origin` is `Global` (a user-created global variable), `Core` (a microscope-state
variable), or another node's name (that node's output variable). See
`glados_pycromanager/Documentation/UserManual.md` (section on Glados variables)
for the user-facing explanation and the `Showcase_Variables_1.json` example
recipe.

Switching the combo box calls `hideAdvVariables()`, which shows/hides the three
widget groups **purely by matching the `#`-delimited object-name prefix**
(`LineEdit`, `LineEditVariable`/`PushButtonVariable`, `LineEditAdv`/`PushButtonAdv`)
against the combo box's current text — it does not check the Qt widget class.
This is *why* the bool checkbox in §3 can reuse the exact same `LineEdit#...`
name and slot into the switch without any change to `hideAdvVariables`.

Whenever a widget's value changes, `changeDataVarUponKwargChange()` copies its
current value into `parentObject.currentData[<objectName>]` (a plain dict on the
panel widget). All downstream readers — `getFunctionEvalTextFromCurrentData_RTAnalysis_init/_run/_end/_visualisation()`
and `getEvalTextFromGUIFunction()` — read from this `currentData` dict by object
name, never from the widgets directly. **Any new widget kind used for a kwarg's
Value mode must therefore be wired into `changeDataVarUponKwargChange()`
(add an `isinstance(...)` branch) or its value will never reach `currentData`.**

## 3. Bool kwargs: checkbox instead of free-text "True"/"False"

Kwargs declared `"type": bool` in `__function_metadata__()` get a `QCheckBox`
for their **Value**-mode widget instead of a `QLineEdit`, built by
`createValueEditWidget(functionname, kwargname)` and wired up by
`wireValueEditWidget(line_edit, defaultValue)` (both in `GUI/utils.py`, used from
`layout_init()` for both required and optional kwargs). The checkbox:

- keeps the object name `LineEdit#<function>#<kwarg>` (same convention as every
  other Value-mode widget), so `hideAdvVariables()` and the Value/Variable/Advanced
  switch keep working unmodified,
- is checked/unchecked from the metadata `"default"`,
- reports its state through `changeDataVarUponKwargChange()` (extended with a
  `QCheckBox` branch) as the string `"True"`/`"False"` — i.e. **exactly the same
  string** that used to come from a user typing `True`/`False` into the old
  `QLineEdit`. This keeps every downstream consumer (`getEvalTextFromGUIFunction()`,
  the node's own `kwargs.get('X', default)` parsing) byte-for-byte unaffected.

Variable and Advanced modes for a bool kwarg are unchanged: they are still typed
as text (`myBoolVar@Global` or `{myBoolVar@Global}`), since a variable/expression
reference is not itself a boolean literal.

**If you add a new typed widget** (e.g. a `QComboBox` for an enum-like kwarg, a
`QSpinBox` for int), follow the same pattern:
1. Branch on `typeFromKwarg()` in `createValueEditWidget()`.
2. Keep the object name `LineEdit#<function>#<kwarg>`.
3. Handle the new widget class in `wireValueEditWidget()` (default value + change
   signal) and in `changeDataVarUponKwargChange()` (how to read its current value
   as a string).
4. Do not touch `hideAdvVariables()` — it is already widget-class-agnostic.

## 4. Two paths out of `currentData`: the eval-text path and the binder

`_rtAnalysisKwargsFromCurrentData()` (`GUI/utils.py`) is the single scanner that
turns a panel's `currentData` dict into `(methodName, kwargNames, kwargValues,
kwargModes)`. Two consumers take it from there:

- **`getEvalTextFromGUIFunction()`** — the original: builds a Python call
  expression as *text*, which `autonomous/registry.py`'s
  `dispatch_from_eval_text()` re-parses and evaluates. Still used by the
  Analysis-measurement / recipe paths.
- **`bindKwargsFromGUIFunction()`** (T-G2/T-G3) — returns a `BoundKwargs`
  instead: the constants, each coerced by `coerceKwargValue()` to the `"type"` its
  metadata declares, plus one zero-arg closure per Variable-mode kwarg.
  `.resolve()` gives the dict to splat into the node, re-reading every Variable
  kwarg so one changed mid-run is seen. This is what the RT-analysis path uses
  (node construction as of T-G2; `run`/`visualise`/`end` as of T-G4).

  A Variable closure captures the *container mapping* — `nodzInfo.globalVariables`
  / `nodzInfo.coreVariables` / the origin node's `variablesNodz` — never the value
  and never the per-variable dict, because writers replace that dict wholesale
  (`globalVariables[name] = {}`, then `['data'] = value`).

### What coercion changed

`"type"` used to pick a widget class and nothing else: the value travelled to
the node as a string and was re-parsed inside the node body
(`float(kwargs.get(...))`, `str(...).lower() in ('true','1')`). Nodes may keep
that defensive parsing — it works on typed values too — but they can now rely on
receiving a real `int`/`float`/`bool`. One live bug this fixed: `LogScale="False"`
is a *truthy string*, so a node doing a bare `if self.log_scale:` treated an
unchecked checkbox as checked.

Coercion is **permissive**: a value that does not convert cleanly is passed
through as the original string with a warning naming the node and kwarg, so no
existing recipe changes behaviour. A kwarg that declares no `"type"`, or declares
`str` / `'fileLoc'`, is never touched.

### Value / Variable / Advanced, per path

| | required kwarg | optional kwarg |
|---|---|---|
| `getEvalTextFromGUIFunction` | Variable resolved to an unquoted expression; **Advanced unimplemented** (`logging.error('To implement!')`, falls back to a quoted literal) | **mode ignored entirely** — the raw widget text is always quoted as a string literal |
| `bindKwargsFromGUIFunction` | Variable read live via `resolveNodzVariable()`; Advanced unimplemented, same fallback | Variable **is** honoured, same as required |

Honouring the mode for optional kwargs in the binder is a deliberate fix of the
old asymmetry (T-G2), not an accident: a user who picks Variable mode for an
optional kwarg previously got the literal string `"WaitTime@Global"` passed to
the node. It is safe because `resolveNodzVariable()` falls back to that same raw
reference text (with a warning) whenever there is no graph to resolve against —
e.g. an RT node started from the live view, where `nodzInfo` is None.

**Advanced (`{name@Origin}`) mode is still unimplemented on both paths.**
