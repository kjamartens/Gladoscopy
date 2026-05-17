# Contributing to Glados-PycroManager

Thanks for your interest. This project is a Windows-first, PyQt5/napari
research tool, and Python 3.13 is hard-required (`pyproject.toml`).
Please read the relevant section before you open a PR.

## Quick start

```pwsh
# 1. Clone, then create the conda env (Windows one-shot):
.\win_create_env.bat
# 2. ...or manually:
conda activate GladosEnv
pip install -e ".[dev]"
# 3. Optional but recommended:
pre-commit install
```

`make help` lists the common dev tasks (test, lint, format, run, …).
The `Makefile` works under Git-Bash on Windows.

## Where things live

A one-paragraph-per-module map lives at `docs/module-map.md`. Larger
design decisions are recorded under `docs/adr/`. The active
optimization plan is in `claude_project.md` and is driven by Claude
Code via the *continue* protocol documented in `CLAUDE.md`.

If you are adding a new autonomous-microscopy node, read both:
- `glados_pycromanager/AutonomousMicroscopy/` — code-side discovery
  contract.
- `CLAUDE.md` — explains the plugin discovery mechanism (source folder
  *and* the user's AppData folder).

## Branching & commits

- Default branch: `main`. Long-lived work-in-progress: `Code-cleanup`.
  The active optimization branch is `claude_optimization` (see
  `claude_project.md`).
- Commits follow Conventional Commits:
  `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `tool`,
  `ci`, `style`, `reliability`, `security`, `release`, `ux`, `build`.
- Keep commits small and atomic. The optimization plan does one commit
  per step; treat that as the project norm.

## Tests

```pwsh
make test          # equivalent to: python -m pytest -q
```

Tests live under `tests/`. They must run **without** real hardware —
use `tests/fakes/` (after Phase 5) or `unittest.mock`. If you add a
test that hits a Qt widget, use `pytest-qt`. The pytest config in
`pyproject.toml` disables the auto-loaded napari plugins (they hang for
10+ minutes via the project's own napari manifest); leave that disabled.

## Lint, format, types

```pwsh
make lint          # ruff check + mypy (informational)
make format        # ruff format
make lint-fix      # ruff check --fix
```

The vendored Nodz editor at `glados_pycromanager/GUI/nodz/` is
**excluded from refactors, lint auto-fixes, and type checks** — leave
it untouched so we can re-sync with upstream.

`mypy` is informational right now (Phase 15 of the plan introduces
typed modules). Only `slack_settings_dialog.py` and the
`microscopeInterfaceLayer.py` are checked by the pre-commit `mypy` hook.

## Security

See `SECURITY.md` for vulnerability reporting and the historical
exposure log (a stale Slack token was hard-coded prior to 2026-05).
Do not paste credentials into source — use the **Slack settings…**
dialog and let the values persist into per-user AppData.

## Pull requests

- Target `main` (or `Code-cleanup` if your work feeds the long-lived
  cleanup branch — coordinate first).
- CI must pass. Lint and mypy are informational; **tests are the
  blocking gate**.
- Reference any related ADR or `claude_decisions.md` entry in the PR
  body — it helps future readers understand intent.

## Adding a new autonomous-microscopy node

1. Drop a `.py` file into one of:
   - `glados_pycromanager/AutonomousMicroscopy/Analysis_Measurements/`
   - `glados_pycromanager/AutonomousMicroscopy/Real_Time_Analysis/`
   - `glados_pycromanager/AutonomousMicroscopy/CustomFunctions/`
   …or into the matching subfolder under
   `<AppData>/Glados-PycroManager/` (no source-tree edit required).
2. The file's top-level functions need a `__function_metadata__()`
   accessor — see existing examples (`AverageImage.py`).
3. Test it loads via the plugin-discovery path (Phase 5 of the plan
   ships `tests/test_plugin_discovery.py`).

## License

By contributing you agree your contribution will ship under the same
GPLv3 license as the project (`LICENCE` in repo root).
