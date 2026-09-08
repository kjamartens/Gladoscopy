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

## 4. Known pre-existing limitation (not introduced by the checkbox change)

`getEvalTextFromGUIFunction()` (`GUI/utils.py`) builds the eval-text sent to
`autonomous/registry.py`'s `dispatch_from_eval_text()`. For **required** kwargs it
special-cases Variable mode (emits an unquoted `nodzInfo.globalVariables['X']['data']`-style
expression) — but not Advanced mode (`logging.error('To implement!')`, falls back
to a quoted literal). For **optional** kwargs — which is where every bool kwarg in
this codebase lives — the Value/Variable/Advanced mode is **ignored entirely**:
the raw widget text is always wrapped in quotes as a string literal
(`LogScale="True"`, or `LogScale="WaitTime@Global"` if Variable mode was
selected without it being resolved). This is a pre-existing gap unrelated to the
checkbox widget change; a node's `kwargs.get('SomeBool', default)` should
defensively parse a possible string (see `WindowTaper` handling in
`AutonomousMicroscopy/Real_Time_Analysis/FFT_im.py`) rather than assume a real
Python `bool`. Fixing the optional-kwarg eval-text quoting is out of scope here
and should be a separate, deliberate change (it affects every optional kwarg of
every type, not just bools).
