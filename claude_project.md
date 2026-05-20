# claude_project.md — Gladoscopy / Glados-PycroManager optimization plan

This document is the master plan for Claude Code to optimize the Glados-PycroManager
codebase. It is structured in five sections matching the user's request:

1. Understanding the code and pain points
2. What is missing (traditional + AI-collaboration POV)
3. Detailed change list (no implementation yet)
4. Performance / UX / DX optimization ideas
5. **Actionables** — phased, step-by-step roadmap to execute on a new
   `claude_optimization` branch with small atomic commits

A "continue" workflow is also defined: whenever the user says **continue**,
Claude should first read `claude_issues.md` and resolve any unchecked issues
before progressing to the next actionable step. Non-trivial choices made
while executing steps are recorded in `claude_decisions.md`. See the matching
addition in `CLAUDE.md`.

### Interpretation check (read before starting)

Claude's reading of the user's request, written out so it can be corrected:

- **Branch**: One branch `claude_optimization`, already cut from
  `Code-cleanup` at the start of this session. All plan work happens there.
- **Commits**: Small and atomic — roughly one commit per row in the
  Actionables tables. Conventional-commits style.
- **"Continue" protocol**: On the user's "continue", Claude reads
  `claude_issues.md` first, resolves every unchecked item, then advances to
  the next un-committed step in the plan, stopping at each phase's
  verification gate.
- **Slack credentials**: User has confirmed the token is stale/expired.
  Phase 2 simply removes the hard-coded defaults and adds a small GUI
  dialog so the user can enter values at runtime — no out-of-band rotation
  step is enforced.
- **Vendored Nodz**: `glados_pycromanager/GUI/nodz/` is treated as
  third-party and is **excluded** from refactors, lint auto-fixes, type
  passes, and error-handling sweeps. Ruff/mypy configs add it to their
  exclude lists.
- **Error handling (Phase 9)**: Phase 9 does **both** (a) tighten existing
  bare/broad `except:` blocks **and** (b) add new validation/error-checks
  at module boundaries that currently have none. Each new check ships with
  positive and negative-path tests.
- **Decisions log**: Every non-trivial choice taken during step execution
  is appended to `claude_decisions.md` in the same commit as the change.

If any of the above does not match what the user wants, the user should say
so before the next "continue" — corrections become decision entries.

---

## 1. Understanding the code

### 1.1 What this project is
- **Glados-PycroManager** is a Napari-based UI on top of Pycromanager (a Python
  wrapper around Micro-Manager) plus a node-graph framework for *autonomous
  microscopy* (segmenting/scoring/acquiring without manual intervention).
- It runs **either standalone** (own `QApplication` via the `glados*` console
  scripts → `GUI/GUI_napari.py:main`) **or as a Napari plugin** (entrypoint
  `_dock_widget.py:MainWidget`).
- Three mutually-exclusive Micro-Manager backends are abstracted behind
  `MicroscopeInterfaceLayer` (MIL): `PYCROMANAGER_JAVA`, `PYCROMANAGER_PYTHON`,
  `MMCORE_PLUS`. User picks the backend in a small startup dialog.
- Cross-component state lives on a single `Shared_data` object passed everywhere.
- Autonomous recipes are JSON files edited in a vendored Nodz graph editor;
  nodes are auto-discovered from `Analysis_Measurements/`, `Real_Time_Analysis/`,
  and `CustomFunctions/` (both source folders and the user's AppData dir).

### 1.2 Codebase scale
About **26 600 lines of Python across 45 files**, with several god-files:

| File                                        | Lines |
|---------------------------------------------|------:|
| `GUI/FlowChart_dockWidgets.py`              | 6 285 |
| `GUI/utils.py`                              | 3 860 |
| `GUI/nodz/nodz_main.py` *(vendored)*        | 3 497 |
| `GUI/MMcontrols.py`                         | 2 138 |
| `Core/MDAGlados.py`                         | 1 860 |
| `GUI/napariGlados.py`                       | 1 343 |
| `GUI/AnalysisClass.py`                      |   918 |
| `Core/microscopeInterfaceLayer.py`          |   669 |
| `GUI/custom_widget_ui.py`                   |   711 |
| `GUI/LaserControlScripts.py`                |   552 |

Anything north of ~1 500 LOC for a single module is a strong signal that
responsibilities should be split.

### 1.3 What is already optimized / good
- Strong **backend abstraction** (`MicroscopeInterfaceLayer`) — one of the
  cleanest pieces of the codebase.
- **Single shared-state object** (`Shared_data`) — sensible architecture for a
  PyQt + napari hybrid; avoids globals.
- **Dataclass-based config** with rich field metadata (display name, input
  widget type, options) — enables the auto-generated settings UI.
- **Plugin auto-discovery** for autonomous-microscopy nodes via the
  `Analysis_Measurements/`, `Real_Time_Analysis/`, `CustomFunctions/` packages
  → users drop a `.py` into AppData and it appears as a node.
- **Async napari rendering** is opted-in (`NAPARI_ASYNC=1`, `NAPARI_OCTREE=1`).
- **Console-script ergonomics**: four aliased commands all hit the same entry
  point, plus a napari-plugin entrypoint and an IDE-direct entrypoint.
- A small **pytest scaffold** exists (`tests/`) with `pyproject.toml` config.
- **CLAUDE.md** already exists and is high quality (backend mental model,
  shared-state convention, plugin discovery quirk, sys.path shim explanation).
- A `Documentation/` folder ships with the package and is referenced from
  `napari.yaml` (User Manual command).

### 1.4 Pain points (highest-impact first)

#### Security
1. **Hard-coded Slack token + signing secret** in
   `GUI/sharedFunctions.py:WebhookConfig` defaults — these look like real
   credentials checked into git. Must be revoked + moved to environment vars
   or the user's `glados_state.json` (already loaded as override).
2. **70+ uses of `eval()`** — the autonomous-microscopy engine builds Python
   call strings and `eval`s them. This is both a security and a maintainability
   issue. There is no untrusted-input path today, but a recipe JSON authored
   by a third party would be a code-execution vector.

#### Reliability / correctness
3. **131 bare or broad `except:` blocks** — many silently swallow errors with
   only `pass` or a debug log. Examples in `utils.py`, `sharedFunctions.py`,
   `napariGlados.py`. Real failures (config corruption, hardware loss) are
   invisible.
4. **`AutonomousMicroscopy/MainScripts/Main.py`** is a *script with side
   effects at module scope* (calls `plt.show()`, opens hardcoded test TIFFs).
   It is included in the package; importing it accidentally would block on a
   matplotlib window. It looks like committed scratch code.
5. **Plugin discovery is opaque**: `__init__.py` files in
   `Analysis_Measurements`/`Real_Time_Analysis`/`CustomFunctions` mutate
   `__all__` while iterating it, use `exec()` strings to import, and inject
   names into `globals()` via `importlib`. Failures are silently downgraded
   (`except ModuleNotFoundError`). Hard to debug, hard to test.
6. **String-based call building in `HelperFunctions`** (`createFunctionWithArgs`
   doubles the function name → `"foo.foo()"`) is implicitly tied to a
   `module.function` naming convention that is not documented or validated.
7. **`napariGlados.py:97` has a TODO acknowledging a 2-second hot-path stall**
   in the live update loop — that is the kind of issue the user will feel
   every session.

#### Code quality / structure
8. **God-files** (see table above). `FlowChart_dockWidgets.py` and `utils.py`
   each carry unrelated concerns; splitting them is necessary before any
   refactor can be done safely.
9. **`utils.py` is a junk drawer**: PyQt widget builders, dataclass JSON I/O,
   plugin discovery helpers, file-cleanup, web-engine markdown rendering — all
   in one module.
10. **`MicroscopeInterfaceLayer.MI()` is called 2–3× per method** (e.g.
    `clear_roi`, `get_auto_shutter`) — each call re-runs `isinstance` checks
    and Java-bridge attribute inspections. Should be cached once at
    `set_core()` time.
11. **Heavy import-time work** in many modules:
    - `GUI_napari.py` imports tensorflow/napari/all autonomous nodes at top
      level → very slow startup.
    - `utils.py` imports `pycromanager.Core` at module scope → import-time
      Java bridge wakes up.
    - `Analysis_Measurements/__init__.py` does an `os.walk` of AppData on
      import.
12. **Repeated `sys.path.insert` shim** copy-pasted across many files. There
    is one canonical pattern; turn it into a single utility or rely entirely
    on the editable install.
13. **Mix of `logging` and `loguru` and `print()`** (95 print calls) — CLAUDE.md
    says "prefer `logging` for consistency" but the codebase doesn't follow
    that.
14. **Strict pin set** in `pyproject.toml` (`numpy==2.2.6`, `pandas==2.3.1`,
    `tensorflow==2.20.0`, …) — keeps the env reproducible but makes any
    security/bugfix update a major project. No `requirements-dev.txt` or
    `constraints.txt` separation.
15. **`MainScripts/Main.py` references `'./AutonomousMicroscopy/...'`
    relative paths** that only exist if you launch from the repo root —
    further evidence it is a dev scratch file.
16. **`Test.py` and `test.ipynb`** at the repo root (DIPlib FFT bench / scratch
    notebook) are unrelated to the test suite and clutter the project.
17. **`scalene-profile.html` (34 MB) and `scalene-profile.json` (34 MB) are
    committed to git** — repo bloat. Should be in `.gitignore`.

#### Tests / CI
18. **Coverage is essentially zero** outside `HelperFunctions` string builders
    and the MIL backend-detection enum. There is no GUI smoke test, no
    plugin-discovery test, no MDA logic test, no integration test.
19. **No CI** (`.github/workflows/` is absent). Tests are never run on push.
20. **No lint/format config** (no `black`, `ruff`, `flake8`, `isort`, `mypy`).
    Code style drifts between modules.
21. **No pre-commit hooks**.

#### Docs / onboarding
22. **UserManual.md says Python 3.10**, but `pyproject.toml` requires
    `>=3.13, <3.14`. The manual is stale (CLAUDE.md already flags this).
23. **`Documentation/index.html`** is the developer doc but is a generated
    artifact checked into git rather than a markdown source. Hard to keep in
    sync.
24. **No CONTRIBUTING.md, CHANGELOG.md, CODE_OF_CONDUCT.md, SECURITY.md**.
25. **No CLAUDE.md guidance** beyond the project overview — no slash commands,
    no agents, no skills, no hook documentation, no architectural decision
    records.
26. **No `py.typed` marker**, very partial type annotations, no `mypy`
    config — IDE autocompletion is weak.

---

## 2. What is missing for "high standards"

### 2.1 Traditional software-engineering POV

**Testing**
- Unit tests for `MicroscopeInterfaceLayer` against a **fake/mock backend**
  (currently only enum detection is tested).
- Unit tests for `Shared_data` config load/save round-trip
  (`load_config_from_json`, `storeSharedData_GlobalData`).
- Unit tests for the **plugin discovery loader** (verify a `.py` dropped into
  a temp AppData folder gets discovered without `exec()` quirks).
- Unit tests for `FunctionHandling` / `HelperFunctions` *metadata* parsing
  (the regex-based `kwargsFromFunction`, `infoFromMetadata`).
- Unit tests for **MDA event construction** (`Core/MDAGlados.py`) — pure
  Python event-list builders should be testable without hardware.
- **Smoke test**: import the package, build `Shared_data`, and verify each
  dock-widget can be instantiated against a mocked core.
- **Headless GUI test** for the napari plugin path (using `pytest-qt` and a
  fake `MicroscopeInterfaceLayer`).
- **End-to-end** test that loads `Showcase_Basic1.json` recipe and runs it
  against the fake backend.

**Static analysis**
- `ruff` (or `flake8` + `isort`) + `black` formatting.
- `mypy` with a *gradual* config (start with `--ignore-missing-imports`,
  tighten module by module).
- `bandit` for security scanning (will flag the eval usage and hardcoded
  secrets).

**CI/CD**
- GitHub Actions workflow: `lint → test → build wheel`.
- Run tests on Windows (this is a Windows-first project — `win_create_env.bat`
  and PyQt5 hints).
- Build the wheel as an artifact on tag pushes.
- Optional: smoke-test the napari plugin entry point in headless mode.

**Reproducibility**
- A `requirements.lock` (or `uv.lock`) checked in so two installs match
  byte-for-byte.
- Pin policy: hard pin only the GUI-sensitive stack (napari, pyqt5,
  pyqtgraph), loose pin (`~=`) for the rest.
- A `Makefile` or `tasks.py` / `scripts/` with the common commands
  (`make test`, `make lint`, `make run`).
- Docker / devcontainer optional, but a `scripts/dev-setup.ps1` to replace
  the bat-file plus uv is a clear win.

**Project hygiene**
- `CONTRIBUTING.md` with branch/PR conventions, how to run tests, how to
  add a node.
- `CHANGELOG.md` (Keep-a-Changelog format).
- `CODE_OF_CONDUCT.md`.
- `SECURITY.md` describing how to report vulns and the rotation policy after
  the Slack-token leak.
- `.gitignore` updated to exclude `scalene-profile.*`, `*.docx`, lock files,
  `.venv/`, `~$*`.
- Remove the committed 34 MB profile files from history (`git filter-repo`).
- Move `Test.py` / `test.ipynb` to a `scratch/` dir excluded from the wheel.

**Packaging**
- `pyproject.toml [tool.setuptools.package-data]` has duplicated/odd entries
  (`"/Documentation/*"`, `"/*"`) — fix to `setuptools.packages.find` and
  explicit data globs.
- Mark a `py.typed` once types stabilize.

### 2.2 AI-collaboration POV

**Hooks into understanding the code**
- Expand `CLAUDE.md` with: invariants ("anything cross-thread must touch
  `Shared_data`, never globals"), forbidden patterns (`eval`, bare `except`),
  preferred logging conventions.
- Add **ADRs (Architectural Decision Records)** under `docs/adr/` for the big
  decisions: MIL existence, plugin auto-discovery via AppData, Shared_data
  single-object pattern, choice of Nodz, Python 3.13.
- A **module map** (`docs/module-map.md`) — a one-paragraph blurb per file
  with its responsibilities; useful for Claude to load only the relevant
  context.

**Claude Code specific**
- Add `.claude/commands/` slash commands:
  - `/run-tests` → `pytest -q`
  - `/lint` → ruff + mypy
  - `/profile-startup` → `python -X importtime -c "import glados_pycromanager.GUI.GUI_napari" 2>startup.log`
  - `/new-node <Type>` → scaffolds a new analysis/RT/custom node from a
    template.
- Add `.claude/agents/` with at least:
  - `code-reviewer` — reviews diffs against the project rules.
  - `test-author` — drafts pytest cases for a changed module.
  - `node-doctor` — validates that a new autonomous-microscopy node has
    `__function_metadata__`, kwargs documented, and is loadable.
- Pre-allow common read/safe commands in `.claude/settings.json`
  (`pytest`, `ruff`, `mypy`, `git status`, `git diff`) to reduce permission
  prompts.
- Hooks: a pre-commit hook that blocks `print(` and bare `except:` in changed
  files; a `Stop` hook that runs `pytest -q tests/` before yielding control.

**Memory / persistent context**
- Save in Claude memory: this is a Windows-first PyQt5/napari project that
  must remain Python 3.13. Encode that constraint so future sessions don't
  suggest a 3.12 downgrade.

---

## 3. Detailed change list (no implementation yet)

For each item, the change is described as it would appear in a code review.

### 3.1 Security
- **SEC-1**: Rotate the leaked Slack token + signing secret out-of-band.
  Replace the dataclass defaults in `WebhookConfig` with empty strings;
  source from env vars and/or `glados_state.json` only.
- **SEC-2**: Audit every `eval()` call site. Replace each one that takes
  data sourced from user input or files with a dispatched call:
  `MODULE_REGISTRY[fn_name](**kwargs)`.
- **SEC-3**: Audit every bare/broad `except:` block — convert to
  `except SpecificError:`, log at `error` not `debug`, and re-raise where the
  caller cannot recover.

### 3.2 Architecture / structure
- **ARCH-1**: Cache `MI()` once per `set_core()` call: store
  `self._mi_type: MicroscopeInstance` and have every helper read that.
- **ARCH-2**: Split `GUI/utils.py` (3 860 LOC) into:
  - `glados_pycromanager/io/appdata.py` (load/save JSON state + paths)
  - `glados_pycromanager/ui/widgets/builders.py` (Qt builder helpers)
  - `glados_pycromanager/ui/markdown_view.py` (web-engine + markdown)
  - `glados_pycromanager/plugins/discovery.py` (the AppData loader)
  - `glados_pycromanager/util/fs.py` (temp file cleanup)
  Keep `utils.py` as a thin shim with deprecation warnings until call sites
  are migrated.
- **ARCH-3**: Split `GUI/FlowChart_dockWidgets.py` (6 285 LOC) into
  sub-modules along the Nodz region semantics (Initialisation / Scoring /
  Acquisition) and along the editor/runtime axis (graph build vs graph run).
- **ARCH-4**: Hoist plugin discovery from each
  `__init__.py` into a single, *testable*, *non-exec()-based*
  `plugins/discovery.py:load_node_modules(path)` returning a list of imported
  modules. Each subpackage `__init__.py` becomes one line.
- **ARCH-5**: Replace string-based `createFunctionWithKwargs` + `eval()` with
  a function registry: `register(name)` decorator on each node function,
  `dispatch(name, **kwargs)` for calls.
- **ARCH-6**: Move `_dock_widget.py` widget construction into a small
  factory so the standalone path and the napari-plugin path build the same
  widget tree.
- **ARCH-7**: Delete or relocate `AutonomousMicroscopy/MainScripts/Main.py`
  (it is dev scratch with side effects at import). At minimum guard it under
  `if __name__ == "__main__":`.

### 3.3 Performance
- **PERF-1**: Lazy-import heavy deps (tensorflow, csbdeep, stardist,
  bioimageio, dask). Use `importlib.util.find_spec` at startup, only import
  on first use.
- **PERF-2**: Defer the AppData walk in plugin `__init__.py` until first
  node menu open.
- **PERF-3**: Investigate the 2-second hot path flagged by the TODO in
  `napariGlados.py:97`. Likely cause: Java-bridge attribute fetch in the
  live-render generator. Cache or move off the UI thread.
- **PERF-4**: Replace the per-call `isinstance` dispatcher in `MIL` with a
  dict of bound methods set once in `set_core()`.
- **PERF-5**: Use `appdirs` (or `platformdirs` — the modern replacement)
  exactly once at boot and stash the path on `Shared_data` to avoid repeated
  filesystem joins.
- **PERF-6**: Profile startup with `python -X importtime`; eliminate the
  top-10 slowest imports.

### 3.4 Reliability
- **REL-1**: Wrap every `Shared_data` JSON write in a temp-file + atomic
  rename so a crash mid-write does not corrupt user state.
- **REL-2**: Add a "settings schema version" field and a small migrator —
  the dataclass set will evolve.
- **REL-3**: Surface plugin-load failures in a notifications dock instead of
  silent `pass`.
- **REL-4**: Standardize on `logging` (per CLAUDE.md). Replace `loguru` and
  `print()` site by site.

### 3.5 Tests
- **TEST-1**: A `tests/fakes/fake_mil.py` implementing the MIL public
  surface against in-memory state.
- **TEST-2**: `tests/test_plugin_discovery.py` — tmp_path fixture, drop a
  `Foo.py` with `__function_metadata__`, assert it is loaded.
- **TEST-3**: `tests/test_shared_data_io.py` — round-trip every Config
  dataclass.
- **TEST-4**: `tests/test_mil_dispatch.py` — every public method routes to
  the right backend.
- **TEST-5**: `tests/test_mda_event_builder.py` — pure-Python event
  generation from a synthetic acquisition plan.
- **TEST-6**: `pytest-qt`-based smoke tests for each dock widget.

### 3.6 Tooling
- **TOOL-1**: Add `ruff` config in `pyproject.toml` with sensible rules
  (`E,F,I,B,UP,SIM,PL`).
- **TOOL-2**: Add `mypy` config (`ignore_missing_imports`, gradual).
- **TOOL-3**: Add `pre-commit` config (ruff + mypy + trailing-whitespace +
  end-of-file-fixer).
- **TOOL-4**: Add GH Actions workflow `ci.yml`: matrix on
  windows-latest/Python 3.13, install `[dev]`, run `ruff`, `mypy`, `pytest`.
- **TOOL-5**: `Makefile` (or `tasks.py`) with `test`, `lint`, `format`,
  `run`, `profile-startup`.

### 3.7 Docs / Claude integration
- **DOC-1**: Refresh `UserManual.md` for 3.13.
- **DOC-2**: Convert `Documentation/index.html` source-of-truth to a
  generated artifact from markdown via `_CreateDocumentation.py`; commit only
  the markdown.
- **DOC-3**: Author `docs/adr/0001-mil-abstraction.md`, `0002-plugin-discovery.md`,
  `0003-shared-data.md`.
- **DOC-4**: Author `docs/module-map.md` (one paragraph per top-level file).
- **DOC-5**: Author `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`.
- **DOC-6**: Add `.claude/commands/` (`run-tests.md`, `lint.md`,
  `profile-startup.md`, `new-node.md`).
- **DOC-7**: Add `.claude/agents/` (`code-reviewer.md`, `test-author.md`,
  `node-doctor.md`).
- **DOC-8**: Pre-allow `pytest`, `ruff`, `mypy`, `git status`, `git diff`,
  `git log` in `.claude/settings.json`.

### 3.8 Repo hygiene
- **HYG-1**: Add to `.gitignore`: `scalene-profile.*`, `*.docx`, `~$*`,
  `.venv/`, `uv.lock` (or check it in — decide).
- **HYG-2**: Move `Test.py`, `test.ipynb` to `scratch/` excluded from sdist.
- **HYG-3**: Remove the two 34 MB scalene profiles from history
  (`git filter-repo --path scalene-profile.html --invert-paths`) — this
  rewrites history; coordinate with the user first.

---

## 4. Performance, UX, DX optimization ideas

### 4.1 Startup time
- Lazy-import tensorflow/keras (~2 s cold), csbdeep, stardist, bioimageio,
  diplib. Only import on first use of the relevant node.
- Skip the AppData plugin walk until the autonomous-microscopy dock is
  opened.
- Defer `pycromanager.Core` connection attempt — currently `main()` calls
  `Core()` inside a `try` that catches and falls through to the headless
  dialog, but the `try` itself blocks ~1–2 s when no server is up.
- Show a splash earlier: today the splash appears inside `headlessGUI`
  *after* the noisy print sequence in `main()`. Move it to the very first
  Qt event.

### 4.2 Runtime
- Cache the result of `MI()` (see ARCH-1, PERF-4).
- Replace per-frame `np.array(python_list, dtype=object)` in
  `java_arr_to_numpy` with `np.fromiter` on an explicit dtype where possible.
- Move all heavy analysis (StarDist, FFT, BIMZ) off the UI thread via
  `napari.qt.thread_worker` — many of these already use it, audit the rest.
- Use `asyncio` (or `QThreadPool` with futures) for the autonomous-microscopy
  scoring stage so independent scoring nodes evaluate in parallel.

### 4.3 Debug info / observability
- Single structured-logging setup in `utils.set_up_logger()` writing both a
  rotating file (AppData) and the console.
- A "diagnostic dump" command that writes Python version, OS, backend choice,
  config, and last 200 log lines to a single zip — easier bug reports.
- Per-thread log prefixes for the analysis worker threads.
- A `--profile` CLI flag that wraps `main()` in `cProfile` and writes to
  AppData.

### 4.4 User-friendliness
- Validate Micro-Manager path / config file in the headless dialog with a
  green/red indicator before the Start button is enabled.
- Remember last used backend + paths across runs (already partly done via
  `glados_state.json`, but the dialog defaults could be improved).
- Inline node help: each node already advertises `__function_metadata__`;
  surface it as a tooltip in the Nodz editor.
- Better empty-state for the recipe canvas (a "Load example" button).

### 4.5 Error handling
- Replace bare `except:` with a `glados_pycromanager.errors` module of
  typed exceptions: `BackendError`, `RecipeError`, `NodeLoadError`,
  `ConfigError`.
- Top-level exception hook that writes to log + a user-visible notification.

### 4.6 Expandability
- A documented `Node` base class (or Protocol) with the contract:
  `__function_metadata__`, the call signature convention, returned types.
- A `node-doctor` CLI / Claude agent that validates an authored node before
  it ships.
- A versioned recipe-JSON schema (today recipes are hand-validated).

---

## 5. Actionables

> All work happens on a single new branch named **`claude_optimization`**.
> Every step ends with one small git commit so that progress is reversible
> and bisectable. Each phase ends with a verification gate (tests + clean
> diff) before the next phase begins.

**Status glyphs** (applied to phase headings and to every sub-phase row):

- `[x]` — finished and committed.
- `[~]` — in progress (phase has some completed sub-steps but not all).
- `[-]` — **skipped** intentionally; no commit produced. There must be
  a matching decision entry in `claude_decisions.md` explaining why
  (e.g. the step's intent was already satisfied by a previous commit,
  or the artefact already existed). Use `[-]` instead of `[x]` so a
  skim of the table immediately shows which rows have *no* commit
  behind them.
- `[ ]` — open / not started.

When Claude finishes a sub-step it must flip that row's box to `[x]` in
the same commit (or in the verification-gate commit at end of phase),
flip skipped rows to `[-]` (with a decision-log entry), and flip the
phase heading to `[~]` or `[x]` as appropriate. A phase heading reaches
`[x]` when every row is `[x]` or `[-]` — skipped rows still count as
"resolved". Keep the glyphs in sync with reality — they're the
at-a-glance map of where work stands.

### [x] Phase 0 — Claude architecture setup

**Goal**: Stand up the Claude-collaboration scaffolding so that the
"continue" protocol works, decisions are tracked, and the slash
commands / agents the later phases assume are ready to receive content.
Branch is created in this phase and used from this point on.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 0.1 | Cut `claude_optimization` branch from current HEAD (`Code-cleanup`) — **already done in this session** | Branch exists, in use | `git branch --show-current` returns `claude_optimization` |
| [x] 0.2 | Add `claude_issues.md` (empty template with "Open issues" / "Resolved" sections) | "Continue" protocol has an inbox | Commit `chore(claude): add claude_issues.md` |
| [x] 0.3 | Add `claude_decisions.md` (append-only design/process log, format documented inside) | Decision log live | Commit `chore(claude): add claude_decisions.md` |
| [x] 0.4 | Update `CLAUDE.md` "Optimization plan & continue protocol" section: explicit branch check, pointer to `claude_decisions.md`, decision-recording duty | Future sessions know the protocol | Commit `docs(claude): document continue protocol and decisions log` |
| [x] 0.5 | Add interpretation-check section + revised phase plan in `claude_project.md` (reflects user feedback: Slack-removal-only, nodz left alone, error-checks add+tighten) | Plan matches user intent | Commit `docs(claude): expand claude_project plan with user revisions` |
| [x] 0.6 | Create `.claude/commands/` directory with a placeholder `README.md` listing the commands that will be authored in Phase 16 (`run-tests`, `lint`, `profile-startup`, `new-node`) | Slash-command home exists | Commit `chore(claude): scaffold .claude/commands` |
| [x] 0.7 | Create `.claude/agents/` directory with placeholder `README.md` listing the agents authored in Phase 16 (`code-reviewer`, `test-author`, `node-doctor`) | Agent home exists | Commit `chore(claude): scaffold .claude/agents` |
| [x] 0.8 | Append the Phase 0 decisions made so far to `claude_decisions.md` (branch base, Slack handling, nodz exclusion, error-handling scope) | Decisions logged | Commit `docs(claude): log Phase 0 decisions` |
| [x] 0.9 | Verification gate | All files exist; `git log --oneline` shows the Phase 0 commits; no code changed yet | `ls claude_*.md .claude/commands .claude/agents && git log --oneline` |

### [x] Phase 1 — Branch guardrails & baseline

**Goal**: Baseline the current state and put guardrails in place so the
subsequent code-modifying phases are safe.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 1.1 | `pip install -e ".[dev]"` and run `pytest -q` to capture baseline | Baseline pass count recorded | Commit `chore: record baseline test result` (writes `docs/baseline.txt`) |
| [x] 1.2 | Add `.gitignore` entries: `scalene-profile.*`, `*.docx`, `~$*`, `.venv/`, `*.swp`, `bash.exe.stackdump` (uv.lock — record decision in `claude_decisions.md`) | Profiling/scratch artifacts no longer tracked | Commit `chore: tidy .gitignore` |
| [x] 1.3 | `git rm --cached scalene-profile.html scalene-profile.json` (keep on disk) | ~68 MB unstaged | Commit `chore: untrack scalene profile artifacts` |
| [x] 1.4 | Verification gate | Tests still pass; `git status` clean of incidental tracked files | `pytest -q` green |

### [x] Phase 2 — Remove Slack credentials, add GUI input

**Goal**: Strip the stale committed Slack credentials and replace them with
a tiny settings dialog so the user can fill them in at runtime. Persistence
piggy-backs on the existing `glados_state.json` mechanism. **No** out-of-band
rotation is required (the token is stale per user).

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 2.1 | Replace `WebhookConfig` defaults in `GUI/sharedFunctions.py` with empty strings (`slack_token=""`, `slack_secret=""`, `slack_channel=""`). Keep the `setting(...)` metadata so they remain UI-discoverable | Credentials gone from source | Commit `security: remove stale slack credentials from defaults`; `grep -R "xoxb-" .` empty |
| [x] 2.2 | Add `glados_pycromanager/GUI/slack_settings_dialog.py` — small `QDialog` with three line edits (token / secret / channel) and OK/Cancel. Token field is a password-style line edit | Dialog class exists | Commit `feat(ui): slack settings dialog` |
| [x] 2.3 | Wire a "Slack settings…" menu/button (most natural location is the Webhooks area inside the existing settings dialog, if one exists; otherwise add to the autonomous dock toolbar). On OK, write back to `shared_data.config.webhook_config` and call `storeSharedData_GlobalData` so they persist to `glados_state.json` | Reachable from UI, persisted | Commit `feat(ui): wire slack settings dialog` |
| [x] 2.4 | Add `tests/test_slack_settings_persistence.py` — round-trip the three values through `Shared_data` save/load | Locked in | Commit `test: slack settings persistence` |
| [x] 2.5 | Add a guard at Slack-send call sites: if `slack_token` is empty, log a warning and no-op instead of erroring | No nuisance failures when unconfigured | Commit `reliability: noop slack send when unconfigured` |
| [x] 2.6 | Add `SECURITY.md` (short — how to report vulns, note the rotation history line for the historical Slack token) | File exists | Commit `docs: add SECURITY.md` |
| [x] 2.7 | Add `bandit` to `[project.optional-dependencies].dev`; run `bandit -r glados_pycromanager --exclude glados_pycromanager/GUI/nodz` and store the report at `docs/bandit-baseline.txt` | Baseline known, nodz excluded | Commit `chore: bandit baseline` |
| [x] 2.8 | Inventory every `eval(` call site into `docs/eval-inventory.md` (file, line, what it evals) — feeds Phase 9 | Inventory ready | Commit `docs: inventory eval call sites` |
| [x] 2.9 | Verification gate | `pytest -q` green; `grep -R "xoxb-" .` empty; the dialog opens, accepts input, persists; subsequent launch reads it back | Tests + manual note |

### [x] Phase 3 — Tooling foundation

**Goal**: Wire up lint, format, type-check, CI, pre-commit, Makefile.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 3.1 | Add `[tool.ruff]` config (line-length 100, `E,F,I,B,UP,SIM,PL`, `extend-exclude = ["glados_pycromanager/GUI/nodz"]`); add `ruff` to `[project.optional-dependencies].dev` | `ruff check` runs, skips nodz | Commit `tool: add ruff config` |
| [x] 3.2 | `ruff check --fix --select I,UP glados_pycromanager` (import sorting + pyupgrade only — non-behavioral; nodz already excluded) | Imports sorted, syntax modernized | Commit `style: ruff auto-fix imports and pyupgrade` |
| [x] 3.3 | Add `[tool.mypy]` config (`ignore_missing_imports = true`, `check_untyped_defs = false`, `python_version = "3.13"`, `exclude = "glados_pycromanager/GUI/nodz"`) | `mypy glados_pycromanager` runs (warnings OK), skips nodz | Commit `tool: add mypy config` |
| [x] 3.4 | Add `pre-commit` config (`pre-commit-hooks`, `ruff`, `ruff-format`, `mypy`) and install hooks locally; nodz path excluded via the tools' own configs | Hooks run | Commit `tool: pre-commit config` |
| [x] 3.5 | Add `Makefile` (or `tasks.py`) with `make test`, `make lint`, `make format`, `make run`, `make profile-startup` | Devs have one entry point | Commit `tool: add Makefile` |
| [x] 3.6 | Add `.github/workflows/ci.yml` running on Windows + Python 3.13: install `[dev]`, `ruff`, `mypy`, `pytest` | CI runs on push | Commit `ci: add github actions workflow`; CI run on the branch is green |
| [x] 3.7 | Verification gate | CI green; `pytest -q` green | GH Actions badge / log |

### [x] Phase 4 — Repo hygiene

**Goal**: Remove dev scratch, fix packaging metadata, add docs scaffolding.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 4.1 | Move `Test.py`, `test.ipynb` to `scratch/` and add `scratch/` to `[tool.setuptools.exclude-package-data]` | Repo root cleaner | Commit `chore: move scratch files out of root` |
| [x] 4.2 | Fix `[tool.setuptools.package-data]` globs in `pyproject.toml` (drop the leading-slash entries; use `find:`) | Wheel still builds with same files | Commit `build: clean up package-data globs`; `python -m build` succeeds |
| [-] 4.3 | Update `UserManual.md` Python version reference from 3.10 to 3.13 | Doc matches reality | Commit `docs: bump Python version in UserManual` |
| [x] 4.4 | Add `CONTRIBUTING.md`, `CHANGELOG.md` (with an "Unreleased" entry referencing this branch) | Project hygiene up | Commit `docs: add CONTRIBUTING and CHANGELOG` |
| [x] 4.5 | Add `docs/module-map.md` — one paragraph per top-level module (skip nodz internals; record one line "vendored, see upstream") | Claude has a fast index | Commit `docs: add module map` |
| [x] 4.6 | Add `docs/adr/0001-mil-abstraction.md`, `0002-plugin-discovery.md`, `0003-shared-data.md`, `0004-python-313.md`, `0005-vendored-nodz.md` | ADRs in place | Commit `docs: seed ADRs` |
| [x] 4.7 | Verification gate | CI green; `python -m build` succeeds | Build artifact attached |

### [x] Phase 5 — Test scaffolding

**Goal**: Stand up the test infrastructure refactors will lean on. Tests
here cover *current behavior*, locking it in before refactoring.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 5.1 | Add `pytest-qt`, `pytest-mock` to dev deps | Available | Commit `test: add pytest-qt and pytest-mock` |
| [x] 5.2 | Add `tests/conftest.py` with shared fixtures: `tmp_appdata`, `mock_core`, `fake_mil` | Fixtures available | Commit `test: shared conftest fixtures` |
| [x] 5.3 | Add `tests/fakes/fake_mil.py` — a FakeMicroscopeInterfaceLayer | Tests can substitute hardware | Commit `test: fake microscope interface layer` |
| [x] 5.4 | Add `tests/test_shared_data_io.py` — round-trip Config to JSON | Locks the config schema | Commit `test: shared_data JSON round-trip` |
| [x] 5.5 | Add `tests/test_mil_dispatch.py` — every public MIL method dispatches by backend (parameterized) | Locks MIL behavior | Commit `test: MIL backend dispatch coverage` |
| [x] 5.6 | Add `tests/test_plugin_discovery.py` — drop a `.py` into tmp AppData, assert loadable | Locks plugin contract | Commit `test: plugin discovery from AppData` |
| [x] 5.7 | Add `tests/test_mda_event_builder.py` — pure-Python event list generation | Locks MDA logic | Commit `test: MDA event builder` |
| [x] 5.8 | Verification gate | CI green; new tests all pass | `pytest -q` count higher than baseline |

### [x] Phase 6 — Architecture: MIL caching and plugin discovery

**Goal**: First behavioral refactor, smallest blast radius, fully test-backed.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 6.1 | In `MicroscopeInterfaceLayer.__init__`, add `self._mi: MicroscopeInstance = UNKNOWN`. Update `set_core` to compute it once. Have `MI()/get_MI()/get_microscope_interface()` return the cached value | Faster dispatch, same behavior | Commit `perf: cache microscope interface type in MIL`; `test_mil_dispatch.py` still green |
| [ ] 6.2 | Extract plugin discovery from `Analysis_Measurements/__init__.py`, `Real_Time_Analysis/__init__.py`, `CustomFunctions/__init__.py` into `glados_pycromanager/plugins/discovery.py:load_node_modules(folder, prefix)` | Single, testable implementation | Commit `refactor: hoist plugin discovery into a single module` |
| [x] 6.3 | Each subpackage `__init__.py` becomes 5–10 lines calling `load_node_modules` | Less magic | Commit `refactor: thin plugin __init__ files` |
| [-] 6.4 | Replace the `exec("from .X import *")` with `importlib.import_module` + explicit `globals().update(...)` | No more `exec` on plugin load | Commit `refactor: drop exec from plugin loader` |
| [x] 6.5 | Surface failed plugin loads in a log warning (not silent `except`) | Visible failures | Commit `reliability: log plugin load failures` |
| [x] 6.6 | Verification gate | `test_plugin_discovery.py` + `test_mil_dispatch.py` green; manually start `glados`, confirm nodes still appear | Pytest log + screenshot or note in commit |

### [x] Phase 7 — Split god-files: `utils.py`

**Goal**: Carve `GUI/utils.py` (3 860 LOC) into responsibility modules.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 7.1 | Create `glados_pycromanager/io/__init__.py`, `glados_pycromanager/io/appdata.py`. Move `load_config_from_json`, `storeSharedData_GlobalData`, `cleanUpTemporaryFiles` | New module compiles | Commit `refactor: move AppData I/O into io.appdata` |
| [x] 7.2 | In old `utils.py`, re-export the moved names with a `DeprecationWarning` to avoid breaking callers | Backward compatible | Commit `refactor: utils.py shim re-exports` |
| [x] 7.3 | Create `glados_pycromanager/ui/widgets/builders.py`. Move Qt widget helpers (`createGroupBox`, etc.) | Builders isolated | Commit `refactor: move Qt builders to ui.widgets.builders` |
| [x] 7.4 | Create `glados_pycromanager/ui/markdown_view.py`. Move the QWebEngine markdown viewer code | Markdown view isolated | Commit `refactor: extract markdown viewer` |
| [-] 7.5 | Create `glados_pycromanager/util/fs.py`. Move filesystem helpers | FS helpers isolated | Commit `refactor: extract filesystem helpers` |
| [x] 7.6 | Add a temporary `tests/test_utils_reexport.py` that imports every public name from the old path and the new path and asserts equality | Reexports verified | Commit `test: shim re-export equivalence` |
| [x] 7.7 | Verification gate | CI green; manual smoke test of `glados` startup | Commit `chore: phase 7 verification` referencing test pass |

### [x] Phase 8 — Split god-files: `FlowChart_dockWidgets.py`

**Goal**: Carve the 6 285-LOC flowchart module along its natural seams.
Nodz itself (`glados_pycromanager/GUI/nodz/`) stays untouched.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 8.1 | Read and document the file's regions in `docs/flowchart-regions.md` (a map: lines x–y handle Initialisation pane, y–z handle Scoring graph, z–w handle Acquisition graph, w–end handle the runtime executor) | Plan ready | Commit `docs: flowchart-regions map` |
| [x] 8.2 | Extract pure data classes / enums into `glados_pycromanager/autonomous/types.py` | First slice out | Commit `refactor: extract autonomous types` |
| [x] 8.3 | Extract the JSON recipe load/save helpers into `glados_pycromanager/autonomous/recipe_io.py` | Recipe I/O isolated | Commit `refactor: extract recipe I/O` |
| [x] 8.4 | Extract the runtime executor into `glados_pycromanager/autonomous/executor.py` | Executor isolated | Commit `refactor: extract autonomous executor` |
| [x] 8.5 | The remaining `FlowChart_dockWidgets.py` is the Qt dock + Nodz glue only | God-file < 1 500 LOC | Commit `refactor: trim FlowChart_dockWidgets to glue only` |
| [x] 8.6 | Add `tests/test_recipe_io.py` and `tests/test_executor.py` against `Showcase_Basic1.json` | Locked-in behavior | Commit `test: recipe IO and executor` |
| [x] 8.7 | Verification gate | CI green; manual: open the autonomous dock, load `Showcase_Basic1.json`, no regressions | Smoke note in commit |

### [x] Phase 9 — Replace `eval()` with a function registry

**Goal**: Kill the eval-based dispatch in autonomous microscopy.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 9.1 | Add `glados_pycromanager/autonomous/registry.py` with `@register("Module.Function")` decorator and a `dispatch(name, **kwargs)` function | Registry ready | Commit `feat: autonomous function registry` |
| [x] 9.2 | Decorate all functions in `Analysis_Measurements/` with `@register(...)` (one commit per file: `AverageImage`, `AverageIntensity`, `RandomShapes`, `StarDist_image`, `checkAgainstList`) | 5 small commits | 5 commits `feat: register <node>` |
| [x] 9.3 | Decorate all functions in `Real_Time_Analysis/` (`BioImageModelZoo`, `EndAtFrame`, `FFT_im`, `LaserAdjustment`, `pSMLM`, `RT_counter`, `SharpnessValue`) | 7 small commits | 7 commits |
| [x] 9.4 | Decorate all in `CustomFunctions/` (`AutoFocusBF`, `Strobo_lasers`, `ExampleCustomFunction_DiceRoll`) | 3 small commits | 3 commits |
| [x] 9.5 | Replace each `eval(createFunctionWithKwargs(...))` call site with `dispatch(name, **kwargs)` | Eval-free hot path | Commit per call site (10–15 commits) |
| [x] 9.6 | Keep `createFunctionWithKwargs` for string display only, mark unsafe variants `_str_for_display` | Clear separation | Commit `refactor: rename eval-only string builders` |
| [x] 9.7 | Update `tests/test_helper_functions.py` and add `tests/test_registry.py` | Coverage on the new path | Commit `test: registry dispatch` |
| [x] 9.8 | Verification gate | CI green; manual: run the example recipe end-to-end | Pytest + run note |

### [x] Phase 10 — Error-handling: tighten existing **and** add new checks

**Goal**: Two complementary jobs in this phase:
  (a) drive the 131 bare/broad `except:` count down to near zero by
      tightening existing blocks, and
  (b) **add** new validation/error checks at module boundaries that
      currently have none.
Every new check ships with a dedicated test (positive **and** negative
path). Nodz folder is excluded from this sweep.

**Step 10.0 — audit (run before any code change)**

Produce `docs/error-audit.md` with two tables:
  - Table A: every existing bare/broad `except:` site (file, line,
    proposed narrowed exception, log level).
  - Table B: every *missing* check — module boundaries that currently
    accept anything and silently fail or crash later. Initial seed list:
    1. `Shared_data` JSON load — schema validity, version field,
       corrupted JSON.
    2. `Shared_data` JSON write — atomic temp-file + rename.
    3. Plugin loader — `__function_metadata__` is well-formed,
       function names match, no duplicate registrations.
    4. Recipe loader (`recipe_io.load`) — schema version, required
       region keys, dangling node references.
    5. MIL `set_core` — reject `None`, log when backend is `UNKNOWN`.
    6. MDA event builder — reject impossible plans (negative frames,
       missing channels).
    7. Headless dialog — validate MM app path and config file
       existence before enabling Start.
    8. Slack send — empty token / network failure → log, no raise.
    9. AppData walk — directory missing/unreadable → log and skip.
   10. Node call dispatch — unknown function name → typed error.

**Step list**

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 10.0 | Write `docs/error-audit.md` (Tables A and B above) | Audit complete | Commit `docs: error-handling audit` |
| [x] 10.1 | Add `glados_pycromanager/errors.py` (`BackendError`, `RecipeError`, `NodeLoadError`, `ConfigError`, `NodeDispatchError`, `MDAEventError`) | Typed exceptions exist | Commit `feat: typed exceptions module` |
| [x] 10.2 | **Tighten** bare-except sites one file at a time (one commit per file): `sharedFunctions.py`, `napariGlados.py`, `MMcontrols.py`, `MDAGlados.py`, `FlowChart_dockWidgets.py`, `utils.py` (nodz/* excluded). Each commit pairs with a regression test if the previously-swallowed error was reachable | Narrower excepts, error-level logs, re-raise where appropriate | 6 commits `reliability: tighten except blocks in <file>` |
| [x] 10.3 | **Add** check + tests: `Shared_data` JSON load — corrupted JSON, missing version, future version. Tests: `tests/test_errors_shared_data_load.py` (3 negative cases + 1 positive round-trip) | New defensive boundary | Commit `reliability: validate shared_data JSON on load` |
| [x] 10.4 | **Add** check + tests: atomic JSON write (write to `*.tmp`, `os.replace`). Test: kill-mid-write simulation via monkeypatched `json.dump` raising halfway | Crash mid-write no longer corrupts state | Commit `reliability: atomic shared_data write` |
| [x] 10.5 | **Add** check + tests: plugin loader rejects malformed `__function_metadata__` with `NodeLoadError`. Tests: drop a malformed `.py` into tmp AppData, assert `NodeLoadError` raised and logged | Bad plugins fail loudly | Commit `reliability: validate plugin metadata` |
| [x] 10.6 | **Add** check + tests: `recipe_io.load` validates schema version, required region keys, and node-id references resolve. Tests: 4 negative cases + happy-path on `Showcase_Basic1.json` | Recipes fail fast | Commit `reliability: validate recipe schema on load` |
| [x] 10.7 | **Add** check + tests: `MIL.set_core(None)` raises `BackendError`; UNKNOWN backend logs once. Tests: parameterized over each backend type + None + bogus object | Backend probe stricter | Commit `reliability: stricter MIL.set_core` |
| [x] 10.8 | **Add** check + tests: MDA event builder rejects impossible plans. Tests: negative frame count, missing channel, zero step interval | MDA construction safe | Commit `reliability: validate MDA event inputs` |
| [x] 10.9 | **Add** check: headless dialog validates MM path + config file (file exists, .cfg suffix); Start button disabled otherwise. Test: `pytest-qt` smoke | Fewer bad starts | Commit `reliability: validate headless dialog inputs` |
| [x] 10.10 | **Add** check + tests: Slack send guards empty token (log info, no-op), wraps network errors in `BackendError`. Tests: empty creds, mocked `requests` raising | Slack failure isolated | Commit `reliability: defensive slack send` |
| [x] 10.11 | **Add** check + tests: AppData plugin walk on missing/unreadable directory logs and continues. Test: pass nonexistent path | Loader robust | Commit `reliability: tolerant AppData walk` |
| [x] 10.12 | **Add** check + tests: registry `dispatch` raises `NodeDispatchError` on unknown name. Test: `dispatch("nope")` | Hard failure on bad recipe | Commit `reliability: NodeDispatchError on unknown function` |
| [x] 10.13 | Add a top-level `sys.excepthook` (and a Qt `qInstallMessageHandler`) that logs uncaught exceptions to the AppData log file. Test: simulate an unhandled exception, assert log contains it | Crashes are diagnosable | Commit `reliability: global exception hook` |
| [x] 10.14 | Verification gate | `grep -R "except:" glados_pycromanager --exclude-dir=nodz` returns 0; every new test passes; total test count ≥ baseline + 25 | Grep + pytest summary |

### [x] Phase 11 — Logging unification

**Goal**: One way to log, per CLAUDE.md. Nodz folder skipped.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 11.1 | Centralize logger setup in `glados_pycromanager/observability/logger.py` (rotating file + console + module-level format) | Single setup | Commit `feat: centralized logger` |
| [-] 11.2 | Remove `loguru` imports (one commit per file that uses it) | Single logger lib | Commits `style: replace loguru with logging in <file>` |
| [x] 11.3 | Convert remaining `print(` calls in non-CLI code paths to `logging.info` (skip `main()` startup banner, skip nodz) | 95 → <10 | Commits per file |
| [x] 11.4 | Drop `loguru` from `pyproject.toml` dependencies | Smaller env | Commit `chore: drop loguru dep` |
| [x] 11.5 | Verification gate | `grep -R "from loguru" glados_pycromanager` empty; CI green | Grep + pytest |

### [x] Phase 12 — Startup performance

**Goal**: Measurable startup speedup.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 12.1 | Add `scripts/profile_startup.ps1` (and `make profile-startup`) — wraps `python -X importtime` | Reproducible measurement | Commit `tool: startup profile script` |
| [x] 12.2 | Capture baseline import time → `docs/perf-baseline.txt` | Numbers locked | Commit `docs: startup baseline numbers` |
| [x] 12.3 | Author `docs/lazy-import-strategy.md` — defines the deferred-import contract for node files: (a) class-based RT nodes defer heavy libs to `__init__()`, not `run()`; (b) function-based analysis nodes defer to top of function; (c) a `logging.info("Loading X...")` message always precedes the first local import so the user sees feedback during the run-start pause. | Methodology documented | Commit `docs: lazy-import strategy for autonomous nodes` |
| [x] 12.4 | Implement the strategy throughout: remove heavy deps from module scope in all node files; add deferred imports + feedback messages per the methodology doc (`bioimageio`, `diplib`, `csbdeep/stardist`, `cv2`; drop the dead `csbdeep` import in ExampleCustomFunction_DiceRoll). tensorflow/keras are absent from module scope already. | Faster cold start, no per-frame hangs | Commits per node file |
| [x] 12.5 | Defer the AppData plugin walk until the autonomous dock is constructed | Faster cold start | Commit `perf: defer AppData plugin scan` |
| [x] 12.6 | Capture post-change import time → append to `docs/perf-baseline.txt` | Numbers comparable | Commit `docs: post-optimization startup numbers` |
| [x] 12.7 | Verification gate — 44.6 s → 5.0 s (≈89 % faster); 291 tests pass | New numbers strictly faster; CI green | Diff in baseline file |

### [ ] Phase 12b — Developer workflow completeness

**Goal**: Every common dev action covered by a reliable `make <target>`; a new
contributor can go from zero to green tests in ≤ 3 commands.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 12b.1 | Audit existing `Makefile`: `install` does editable+dev (wrong semantics); `clean` uses `rm -rf` (Unix-only); `profile-startup` writes to `startup.log` in CWD (inconsistent with ps1 script that writes to `docs/`); `verify` covers only lint+tests (no bandit); no `env`, `dev`, `build`, `test-fast`, `test-cov`, `ci` targets | Gap list drives subsequent steps | Document in commit message |
| [x] 12b.2 | Add `pytest-cov>=4.0` to `[project.optional-dependencies].dev` in `pyproject.toml` (needed for `test-cov` target) | Dep available | Commit `build: add pytest-cov dev dep` |
| [x] 12b.3 | Fix `install`/`dev` semantics: `make install` → non-editable prod (`pip install .`); `make dev` → editable + dev extras (`pip install -e ".[dev]"`); add `make env` — idempotent conda env bootstrap (`conda env create` or `conda env update` on conflict); add `make build` — `uv build` to produce wheel + sdist | Semantics match convention | Commit `build: fix install/dev semantics and add env/build targets` |
| [x] 12b.4 | Fix `make clean` for Windows — replace `rm -rf` with a cross-platform Python one-liner (`shutil.rmtree` + `glob`) that also removes any stale `startup.log` | `make clean` works in PowerShell and Git Bash | Commit `build: cross-platform clean target` |
| [x] 12b.5 | Add `make test-fast` (`pytest -x -q`) and `make test-cov` (`pytest --cov --cov-report=term-missing`) | Fast feedback + coverage loop available | Commit `build: add test-fast and test-cov targets` |
| [x] 12b.6 | Add `make ci` that chains `lint bandit test`; make `verify` an alias for `ci` for backwards compat | `make ci` is the one-command local gate | Commit `build: add ci target and keep verify as alias` |
| [x] 12b.7 | Fix `make profile-startup` — delegate to `pwsh -File scripts/profile_startup.ps1` so output goes consistently to `docs/perf-baseline.txt` (the PS1 already does this correctly) | Output path consistent | Commit `build: profile-startup delegates to ps1` |
| [x] 12b.8 | Update `CONTRIBUTING.md` — reflect new targets (`env`, `dev`, `install`, `build`, `test-fast`, `test-cov`, `ci`); add Git-for-Windows `make` path note; update quick-start to `make env && make dev` | Docs current | Commit `docs: update CONTRIBUTING for new Makefile targets` |
| [x] 12b.9 | Verification gate — `make help` lists all targets; 291 tests pass; `make clean` works on Windows (Python shutil); `pytest-cov` dep in pyproject.toml | All green | Commit `chore: phase 12b verification gate` |

### [ ] Phase 13 — Runtime performance (live loop) + napari visualization

**Goal**: Address the 2-second hot-path TODO, parallelize scoring, and optimize napari visualization for all MIL backends.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [x] 13.0 | (Side-quest, requested mid-phase) Add CLI overrides to `GUI_napari.main()` (`--backend`, `--config`, `--mm-path`, `--buffer-mb`, `--max-memory-mb`, `--auto-demo`) so headless tests/profiles bypass the startup popup. Add Makefile `run-mm` (parameterised by `BACKEND`/`CONFIG`/…) and `run-demo` (pymmcore-plus bundled demo). Argparse rejects bad combos. New tests in `tests/test_gui_napari_cli.py` | Headless launch without clicking | Commit `feat: CLI overrides for headless launch (run-mm / run-demo)` |
| [x] 13.1 | Profile `napariGlados.py` live loop with `cProfile` in a smoke session against the demo config; store top-20 in `docs/perf-runtime.txt`. Added `--profile-runtime SECS` to `GUI_napari.main()` (in-process cProfile + QTimer orchestration; watchdog dumps on auto-stop) and `make profile-runtime`. Two onscreen sample runs captured: **433 frames in 15s** and **99 frames in 10s**. Key signals: `napariViewer.add_image` = 1.284s on first call (the "2-second stall"); `MILcore.get_pixel_size_um` cumulative 1.285s across 5 calls (~0.26s each, dominant Java-bridge cost — matches the plan author's hint) | Top-25 stored in `docs/perf-runtime.txt` | Commit `perf: runtime profile baseline` |
| [x] 13.2 | Fix the 2-second stall (line 97); the fix is profile-dependent (likely cache a Java-bridge attribute) | Live FPS up | Commit `perf: fix 2s stall in live update loop` |
| [x] 13.3 | Audit each `@thread_worker` site — anything blocking the UI thread? Move to a worker | Smoother UI | Commit `perf: move <X> off UI thread` (per site) |
| [-] 13.4 | Evaluate parallel scoring in the autonomous executor (independent score nodes can run via `concurrent.futures`) | Scoring speedup | Commit `perf: parallel scoring stage` |
| [x] 13.5 | **Napari visualization audit & strategy** — Fully read `napariGlados.py` and all MIL-backend image-delivery paths (`PYCROMANAGER_JAVA`, `PYCROMANAGER_PYTHON`, `MMCORE_PLUS`). Understand: how images arrive (callbacks, polling, queue), how they reach napari layers, what dtype/shape conversions happen, whether contiguous memory and `layer.data =` vs in-place updates are used, and whether NAPARI_ASYNC/NAPARI_OCTREE are being used effectively. Produce `docs/napari-vis-strategy.md` with: current state per backend, identified bottlenecks (copy overhead, GUI-thread vs worker, refresh rate), and a ranked list of optimizations to implement | Strategy documented; no code change | Commit `docs: napari visualization strategy` |
| [x] 13.6 | **Implement napari visualization optimizations** — Apply the highest-priority items from the strategy doc across all three MIL backends: e.g. in-place ndarray updates (`layer.data[:] = …`), ensuring contiguous C-order arrays before assignment, moving frame decode off the GUI thread if any decode is still happening there, reducing unnecessary layer refreshes. Touch `napariGlados.py` and any backend-specific delivery code | Measurably fewer dropped frames; no regressions | Commit `perf: optimize napari layer updates for all MIL backends` |
| [x] 13.7 | Verification gate + **document the optimization recipe** in `docs/perf-runtime-recipe.md` — how to launch a profile (`--profile-runtime` / `make profile-runtime`), how to interpret `docs/perf-runtime.txt`, gotchas (Qt import ordering vs pymmcore-plus segfault, why we orchestrate in-main rather than via a monkey-patch wrapper script), and a checklist for future runtime-perf passes | Runtime profile after < before; CI green; no visual regressions in napari; recipe doc exists | Commit `docs: runtime perf recipe + phase 13 verification` |
| [x] 13.8 | **Guard `Shared_data.__setattr__` debug log** — `sharedFunctions.py:267` evaluates an f-string containing `{value}` on every single attribute set (including numpy frame arrays), even when DEBUG logging is off. Gate behind `isEnabledFor(DEBUG)` and drop the value repr (attribute name is enough). | No per-attr-set string allocation at INFO/WARNING level | Commit `perf(shared_data): guard __setattr__ debug log behind isEnabledFor check` |
| [x] 13.9 | **Cache `getDimensionsFromAcqData` per-acquisition** — `napariGlados.py` calls `utils.getDimensionsFromAcqData(shared_data._mdaModeParams)` up to 6× per frame update, though the result is invariant for a whole acquisition. Add a `_get_cached_dimensions(shared_data)` helper keyed by `id(_mdaModeParams)` and replace all 6 call sites. | O(n_dims × n_acqdata) work eliminated per frame | Commit `perf(napariGlados): cache getDimensionsFromAcqData result per-acquisition` |
| [ ] 13.10 | **Replace `.tolist().index()` with `np.searchsorted`** — `napariGlados.py` lines ~246, 255, 306, 478 convert a sorted numpy array to a Python list then linear-scan it to find a slice index. `np.unique` guarantees sorted output, so `np.searchsorted` is safe (O(log n), no allocation). | Eliminates list alloc + linear scan per dimension per frame | Commit `perf(napariGlados): replace .tolist().index() with np.searchsorted for slice lookup` |
| [ ] 13.11 | **Cache `self._mi` + `np.asarray` in MIL** — Every method in `MicroscopeInterfaceLayer` calls the trivial `self.MI()` getter 2–3× per call (121 total). Cache as `mi = self._mi` at method entry. Also replace `np.array(self.core.get_image())` with `np.asarray(...)` in the PYTHON/MMCORE_PLUS branches of `get_image()` to avoid an unnecessary copy (downstream callers already call `np.ascontiguousarray()`). | Reduces method-call overhead + one array copy per frame | Commit `perf(MIL): cache self._mi as local var; use np.asarray in get_image to avoid copy` |
| [ ] 13.12 | **Fix visualization worker polling** — `napariGlados.py` visualization worker uses `self._new_image.wait(timeout=0.1)`, waking up 10×/s spuriously. Raise timeout to 1.0 s and add `self._new_image.set()` in `acqModeChanged()` so the worker unblocks promptly when acquisition ends. Also cache `time.time()` once at frame entry in `napariUpdateLive` (currently called 3× for the same elapsed-time check). Old `wait(timeout=0.1)` line kept as comment. | 10× fewer spurious wakeups; eliminates 2 redundant `time.time()` calls per frame | Commit `perf(napariGlados): replace 100ms poll with 1s timeout; cache time.time()` |
| [ ] 13.13 | **Rewrite `getDimensionsFromAcqData` as single-pass** — `utils.py:~3320` iterates `acqData` once per dimension with `np.unique` per pass. Replace with a single-pass `dict.setdefault` + `set` accumulation followed by `sorted()` (preserves the sorted-output contract that `np.searchsorted` requires). | N-pass → 1-pass over acqData | Commit `perf(utils): rewrite getDimensionsFromAcqData as single-pass dict accumulation` |
| [ ] 13.14 | **Verification gate** — Run `--auto-demo --profile-runtime 30`; compare new `docs/perf-runtime.txt` entry against pre-13.8 baseline. Smoke-test: live start/stop ×5, 2-ch/3-t/3-z MDA, profile output must not list `__setattr__` or `getDimensionsFromAcqData` in top-25. | Profile shows measurable improvement; no new exceptions; smoke tests pass | Commit `docs: Phase 13 extended performance pass verification` |

### [ ] Phase 14 — UX polish

Note: Phase 10 may have already handled the `headlessGUI` validation; if so
mark 14.1 done. Tooltips on nodes don't modify Nodz internals — they attach
metadata from outside.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [ ] 14.1 | Validate paths in `headlessGUI`; gray out Start until valid (if not already done in 10.9) | Fewer bad starts | Commit `ux: validate headless paths` |
| [ ] 14.2 | Show the splash *before* the noisy print sequence in `main()` | Better perceived startup | Commit `ux: earlier splash` |
| [ ] 14.3 | Surface plugin-load failures in a notification widget | Visible failures | Commit `ux: plugin failure notifications` |
| [ ] 14.4 | Tooltips on Nodz nodes from `__function_metadata__` (attached from outside nodz, no nodz edits) | Inline help | Commit `ux: node tooltips from metadata` |
| [ ] 14.5 | "Load example recipe" button on empty canvas | First-run wins | Commit `ux: empty canvas CTA` |
| [ ] 14.6 | Verification gate | CI green; manual smoke screenshots | Commit `chore: phase 14 verification` |

### [ ] Phase 15 — Type hints and `py.typed`

Nodz folder is excluded from this phase (already excluded by mypy config).

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [ ] 15.1 | Annotate `Shared_data`, MIL public surface, `errors.py`, `registry.py`, `recipe_io.py`, `executor.py` | Strong types where it matters | Commit per file |
| [ ] 15.2 | Tighten `mypy` config: `disallow_untyped_defs = true` for typed modules only (per-module config) | Gradual typing | Commit `tool: stricter mypy for typed modules` |
| [ ] 15.3 | Add `py.typed` marker | Downstream type-checkers see types | Commit `feat: add py.typed marker` |
| [ ] 15.4 | Verification gate | `mypy glados_pycromanager` exits 0 for the typed module subset; CI green | mypy log |

### [ ] Phase 16 — Claude integration (fill the Phase 0 skeleton)

The skeleton directories were created in Phase 0; this phase fills them.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [ ] 16.1 | Expand `CLAUDE.md`: invariants, forbidden patterns, the registry pattern, the logging convention, the typed-exceptions convention | Claude has the rules | Commit `docs(claude): expand project guidance` |
| [ ] 16.2 | Author `.claude/commands/run-tests.md`, `lint.md`, `profile-startup.md`, `new-node.md` | Slash commands | Commit `claude: add slash commands` |
| [ ] 16.3 | Author `.claude/agents/code-reviewer.md`, `test-author.md`, `node-doctor.md` | Subagents | Commit `claude: add subagents` |
| [ ] 16.4 | Pre-allow `pytest`, `ruff`, `mypy`, `git status`, `git diff`, `git log`, `make test`, `make lint` in `.claude/settings.json` | Fewer permission prompts | Commit `claude: preapprove safe commands` |
| [ ] 16.5 | Verification gate | CI green; slash commands listed in `/help` when run locally | Local run note |

### [ ] Phase 17 — Win64 standalone executable

**Goal**: Package the application as a self-contained `glados.exe` for
Windows x64 that is a drop-in replacement for running `glados` from a
conda/venv, ships the full Python runtime and all scientific dependencies,
and is automatically built by CI on tag pushes.

**Bundler choice rationale (record in `claude_decisions.md`)**:
PyInstaller `--onedir` is the pragmatic choice — mature, tested with PyQt5
and napari, and produces a folder layout that avoids the cold-start penalty
of `--onefile` extraction.  Nuitka would give a faster binary but requires
a full C compile toolchain and has known gaps with tensorflow and napari
plugin wiring.  Decision: PyInstaller `--onedir`.

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [ ] 17.1 | Add `pyinstaller` to `[project.optional-dependencies].dev`; record bundler decision in `claude_decisions.md` | Dep available; decision logged | Commit `build: add pyinstaller dev dep` |
| [ ] 17.2 | Author `glados.spec` — PyInstaller spec with `Analysis` entry point at `glados_pycromanager/GUI/GUI_napari.py`, `--onedir`, `hiddenimports` for every lazy-loaded library (`tensorflow`, `keras`, `stardist`, `csbdeep`, `bioimageio.core`, `diplib`, `cv2`, `napari`, `napari.plugins`), and `datas` for `napari.yaml`, `Documentation/`, recipe JSON files, and any other non-`.py` package data | Spec file ready | Commit `build: add glados.spec` |
| [ ] 17.3 | Add `scripts/build_exe.ps1` — one-command local build: `pyinstaller glados.spec --distpath dist --workpath build/pyinstaller`; prints the path of the produced `.exe` on success | Reproducible local build | Commit `build: add build_exe.ps1 script` |
| [ ] 17.4 | Add `build-exe` target to `Makefile` (calls `scripts/build_exe.ps1`) | `make build-exe` works | Commit `build: Makefile build-exe target` |
| [ ] 17.5 | Add `dist/` and `build/pyinstaller/` to `.gitignore` | Build artifacts not tracked | Commit `chore: gitignore exe build output` |
| [ ] 17.6 | Perform a local build, resolve any missing hidden imports or data files, and iterate the spec until `dist/glados/glados.exe` launches the headless dialog without errors | Exe runs locally | Commit `build: fix spec after local smoke test` (amend spec + decisions entry for each gap found) |
| [ ] 17.7 | Verify that AppData plugin discovery works in the frozen context — add a `sys.frozen` guard in `plugins/discovery.py` if needed so the AppData walk uses the correct path under the extracted bundle | User-dropped nodes load from `.exe` | Commit `build: frozen-context AppData path fix` |
| [ ] 17.8 | Add `.github/workflows/release.yml` — triggers on `push: tags: ['v*']`; runs on `windows-latest` / Python 3.13; installs `[dev]`, calls `make build-exe`, zips `dist/glados/` as `glados-win64.zip`, and uploads it as a GitHub Release asset via `softprops/action-gh-release` | Tagged release produces a downloadable zip | Commit `ci: release workflow builds win64 exe` |
| [ ] 17.9 | Smoke-test the CI workflow on a local `act` dry-run or a test tag (e.g. `v0.0.0-exe-test`) and confirm the artifact uploads; delete the test tag afterwards | Workflow is green | Note in commit or `claude_decisions.md` |
| [ ] 17.10 | Verification gate | `make build-exe` succeeds locally; `dist/glados/glados.exe` launches to the headless dialog; `.github/workflows/release.yml` exists and is parseable by `act`; CI green | Manual run + `yamllint` pass |

### [ ] Phase 18 — Documentation regeneration

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [ ] 18.1 | Convert `Documentation/index.html` to a markdown source under `docs/dev/` and have `_CreateDocumentation.py` emit the HTML as a build step | Source-of-truth in markdown | Commit `docs: markdownize developer docs` |
| [ ] 18.2 | Regenerate HTML; commit only the regenerated artifact | Docs match code | Commit `docs: regenerated developer docs` |
| [ ] 18.3 | Update `UserManual.md` to match the new tooling (Makefile, CI) | User docs current | Commit `docs: refresh UserManual for new tooling` |
| [ ] 18.4 | Verification gate | All docs render; CI green | Screenshot or grep |

### [ ] Phase 19 — Final cleanup and release prep

| # | Step | Expected outcome | Proof |
|---|------|------------------|-------|
| [ ] 19.1 | Delete the temporary `utils.py` shim once all imports point to new homes (grep first) | No legacy shim | Commit `refactor: drop utils.py shim` |
| [ ] 19.2 | Bump version in `pyproject.toml` (e.g. `0.0.2 → 0.1.0`); update `CHANGELOG.md` "Unreleased" → `0.1.0` with date | Release ready | Commit `release: bump to 0.1.0` |
| [ ] 19.3 | Tag candidate `v0.1.0-rc1` locally | Tag exists | `git tag` shows |
| [ ] 19.4 | Final verification: `pytest -q`, `ruff check`, `mypy`, `python -m build`, manual run of `glados` and the napari plugin, manual run of `Showcase_Basic1.json` end-to-end | All green | Commit `chore: final verification` with notes |
| [ ] 19.5 | Open PR `claude_optimization → main` (or `Code-cleanup`, per `claude_decisions.md`) with a summary linking each phase | PR exists | PR URL recorded |

### How to prove progress at any time

After every commit:
- `git log --oneline claude_optimization` shows the running ledger.
- `pytest -q` is the universal "still works" check.
- For perf phases: `docs/perf-baseline.txt` / `docs/perf-runtime.txt` show
  before/after numbers.
- For security: `grep -R "xoxb-"` and `grep -R "except:" glados_pycromanager`
  should reach zero.

### How to resume

When the user says **continue**:

1. Read `claude_issues.md` first.
2. If it has unchecked issues, resolve them (one commit each) before
   anything else.
3. Then look at the most recent commit on `claude_optimization` and identify
   the *next* step in the actionables table that has not yet been committed.
4. Execute that step in a small commit. Stop at the next phase verification
   gate and wait for the user.

---

*End of plan.*
