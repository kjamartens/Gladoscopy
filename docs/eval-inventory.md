# `eval()` call-site inventory

Generated for Phase 2.8 of `claude_project.md`; consumed by Phase 9
(registry replacement) and Phase 10 (validation hardening).

`bandit` counts and categorisation reflect a `git grep -n '\beval\s*('`
sweep over `glados_pycromanager/` on commit `7111b47`. Vendored
`glados_pycromanager/GUI/nodz/` is excluded from Phase 9 work but
included here for completeness.

**Totals**: ~63 `eval(` call sites across 8 files (excluding string
literals and `# eval(` comments). 7 distinct usage patterns; only
**Pattern B** (recipe dispatch) and **Pattern C** (variable parsing) are
both untrusted-input-reachable and security-relevant.

## Pattern A — function-metadata reflection (~25 sites)

`eval(f'{functionName}.__function_metadata__()')` — used to call the
`__function_metadata__()` accessor on a function whose name is known as
a string at runtime. The string comes from recipe JSON / node menu.

**Risk**: code execution if `functionName` is attacker-controlled
recipe content. **Fix in Phase 9**: registry-backed
`get_metadata(name)` lookup (`REGISTRY[name].metadata`) — no eval.

Sites:
- `glados_pycromanager/GUI/utils.py:131, 143, 234, 240, 288, 294, 312, 318, 341, 353, 363, 483, 510, 567, 598, 2734`
- `glados_pycromanager/AutonomousMicroscopy/MainScripts/HelperFunctions.py:54, 66, 100, 106, 152, 163`
- `glados_pycromanager/GUI/FlowChart_dockWidgets.py:3881, 4002`

## Pattern B — recipe call dispatch (~5 sites + commented Main.py uses)

`eval(HelperFunctions.createFunctionWithKwargs(name, **kwargs))` — the
*actual* node execution path. The string is a fully formed
`Module.function(arg1=…, arg2=…)` call assembled from the recipe.

**Risk**: highest — this *is* the recipe execution path. **Fix in
Phase 9**: replace with `registry.dispatch(name, **kwargs)`.

Sites:
- `glados_pycromanager/GUI/FlowChart_dockWidgets.py:3860 (output = eval(evalText)), 3927, 4046, 6297`
- `glados_pycromanager/GUI/utils.py:2675, 2694, 2712, 2725`
- `glados_pycromanager/AutonomousMicroscopy/MainScripts/Main.py:68, 73, 74, 76, 77, 79, 80` — **dev scratch**, removed by ARCH-7

## Pattern C — variable/literal parsing from user-typed text (~10 sites)

`eval(value)` where `value` is a string typed by the user into a Nodz
line-edit, intended to be parsed as a Python literal (number, list,
tuple). Used for global variables, if-statement comparators, kwarg
values.

**Risk**: medium (recipe-author-controlled, but recipe is also code).
**Fix in Phase 9 / 10**: `ast.literal_eval` for the literal-only path;
typed coercion (int/float) for numeric inputs.

Sites:
- `glados_pycromanager/GUI/utils.py:717, 718, 719, 740, 822, 2060`
- `glados_pycromanager/GUI/FlowChart_dockWidgets.py:4540, 4592`
- `glados_pycromanager/AutonomousMicroscopy/Analysis_Measurements/checkAgainstList.py:50, 58, 58`

## Pattern D — comparator / if-statement evaluation (~5 sites)

`eval(f"{a} {operator} {b}")` to evaluate user-built comparisons (Nodz
"if" / "scoring threshold" nodes).

**Risk**: medium. **Fix in Phase 9**: small operator dispatch table
(`{"<": operator.lt, ">": operator.gt, ...}`) — no eval needed.

Sites:
- `glados_pycromanager/GUI/FlowChart_dockWidgets.py:4560, 5712, 5777, 5784, 5800`

## Pattern E — self-attr indirection (2 sites)

`eval('self.new_signal')` — trivially replaceable with the bare
attribute access. Holdover from copy-paste.

Sites:
- `glados_pycromanager/GUI/FlowChart_dockWidgets.py:1426, 1427`

## Pattern F — string-keyed parameter lookup (4 sites)

`eval('pulse_len_'+str(wavelength))` — looks up a local variable whose
name is built from a wavelength. Should be a dict
(`{'488': pulse_len_488, ...}`).

Sites:
- `glados_pycromanager/AutonomousMicroscopy/CustomFunctions/Strobo_lasers.py:95, 96, 97, 98`

## Pattern G — partial-string composition (1 site)

`partialString += eval(specialcase[ps_index])` — builds a string by
eval'ing an indexed entry. Almost certainly replaceable with a lookup.

Sites:
- `glados_pycromanager/GUI/utils.py:2632`

## Pattern H — vendored Nodz (1 site, OUT OF SCOPE)

- `glados_pycromanager/GUI/nodz/nodz_main.py:1493` — Nodz internals;
  see `claude_decisions.md` "Vendored Nodz left alone".

## Pattern I — laser-power dynamic lookup (2 sites)

`eval(kwargs['Laser_power']+".keys()")` / `eval(kwargs['Laser_power'])`.
The kwarg is a literal dict-string from the recipe — same pattern as C,
fixable with `ast.literal_eval`.

Sites:
- `glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/LaserAdjustment.py:106, 116`

## Phase-9 migration order (recommended)

1. **E** (self.new_signal) — trivial, removes 2.
2. **F** (Strobo_lasers dict lookup) — small, contained, removes 4.
3. **G** (utils.py:2632) — small.
4. **C / I** (`ast.literal_eval` swap) — mechanical; removes ~12.
5. **D** (operator dispatch) — small new helper; removes 5.
6. **A** (registry-backed `get_metadata`) — biggest behavioural change;
   removes ~25 once the registry from step 9.1 is in place.
7. **B** (recipe dispatch via `registry.dispatch`) — depends on A, last;
   removes 4 production + 7 Main.py scratch.

After all of the above, the bandit `B307` count for our code should
drop from 100 medium-severity to 0 (Nodz vendored entry excluded).
