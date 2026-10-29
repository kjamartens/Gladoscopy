# Contributing to Glados-PycroManager

Thanks for your interest. This project is a Windows-first, PyQt5/napari
research tool, and Python 3.13 is hard-required (`pyproject.toml`).
Please read the relevant section before you open a pull request.

## Quick start

Needs **git**, **[uv](https://docs.astral.sh/uv/)** and **make**. uv downloads
Python 3.13 itself, so no separate Python install is required.

```bash
make dev      # creates .venv, then an editable install with the dev and docs extras
make test     # verify everything works
```

No manual activation: `make dev` creates a `.venv` in the repository root on
first run and every target uses it from then on.

**Windows**: `winget install astral-sh.uv` and `winget install ezwinports.make`
(GnuWin32 make and Git Bash's make also work). The Makefile uses `uv` from
PATH; without one it bootstraps uv into whatever `python` is on PATH.

Without make, `install_windows.bat` does the same install (no dev extras) and
offers Start Menu shortcuts; it is what the documentation points end users to.

Run `make help` to list every target.

## Where things live

- The [module map](https://kjamartens.github.io/Gladoscopy/module-map/)
  (`docs/module-map.md`) says where to look for what.
- Larger design decisions are recorded as ADRs under `docs/adr/`.
- `CLAUDE.md` holds detailed architecture notes: the threading model, the
  frame path, storage and recipe execution.
- Archived planning documents and decision logs from the 2026 optimization
  work are in `docs/plans/`.

## Adding an autonomous-microscopy node

See [Writing nodes](https://kjamartens.github.io/Gladoscopy/developer/writing-nodes/)
(`docs/developer/writing-nodes.md`). In short:

1. Put a `.py` file in one of
   `glados_pycromanager/AutonomousMicroscopy/{Analysis_Measurements,Real_Time_Analysis,CustomFunctions}/`,
   or, without touching the source, in the matching folder under
   `%LOCALAPPDATA%\Glados-PycroManager\AutonomousMicroscopy\`.
2. Give it a module-level `__function_metadata__()` describing each function
   (see `Analysis_Measurements/AverageIntensity.py`).
3. Decorate every callable function or real-time class with
   `@register("<file stem>.<name>")` from `glados_pycromanager.autonomous.registry`.
   Without it the recipe cannot call it.
4. Keep the module light to import: Glados imports every node at startup, so
   import heavy libraries inside the function. `tests/test_plugin_discovery.py`
   and `tests/test_node_packages_import_light.py` check discovery and import cost.

## Branching and commits

- Default branch: `main`. Work on a feature branch and open a pull request.
- Commits follow Conventional Commits:
  `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `tool`,
  `ci`, `style`, `reliability`, `security`, `release`, `ux`, `build`.
- Keep commits small and atomic.

## Install targets

| Target | What it does |
|--------|-------------|
| `make dev` | Editable install with the dev and docs extras; use this for day-to-day development |
| `make install` | Non-editable install (no extras) |
| `make build` | Build wheel + sdist into `dist/` via `uv build` |

## Tests

```bash
make test          # full suite
make test-fast     # stop on first failure
make test-cov      # with branch coverage report
```

`pytest -m "not slow"` skips the few tests that spawn a real subprocess.
Tests live under `tests/` and must run **without** real hardware: use
`unittest.mock`, or pymmcore-plus' bundled demo camera. Tests that touch Qt
widgets use `pytest-qt`. The pytest config in `pyproject.toml` disables the
auto-loaded napari plugins (they hang the suite through the project's own
napari manifest); leave that disabled.

## Documentation

```bash
make docs          # build the site into site/ (strict: broken links fail)
make docs-serve    # live preview at http://127.0.0.1:8000
```

The site is built from `docs/` (configuration in `mkdocs.yml`) and published
to GitHub Pages by `.github/workflows/pages.yml` on every push to `main`. The
API reference is generated from docstrings; to document a new module there,
add it to `docs/developer/api.md`.

## Lint, format, types

```bash
make lint          # ruff check + mypy (informational)
make format        # ruff format
make lint-fix      # ruff check --fix
make ci            # lint + bandit + tests
```

Ruff still reports many pre-existing findings, so `make lint` and `make ci`
fail on the current code; CI runs ruff and mypy informationally. Do not add
new findings in the code you touch.

The vendored Nodz editor at `glados_pycromanager/GUI/nodz/` is
**excluded from refactors, lint auto-fixes and type checks**; leave it
untouched so it can be re-synced with upstream (ADR 0005).

## Security

See `SECURITY.md` for vulnerability reporting. Do not paste credentials into
the source: use the **Slack settings…** dialog, which stores them in per-user
AppData.

## Pull requests

- Target `main`.
- CI must pass. Lint and mypy are informational; **tests are the blocking
  gate**.
- Mention any related ADR in the pull request description.

## Licence

By contributing you agree that your contribution is licensed under the same
CC BY-NC-SA 4.0 licence as the project (`LICENCE` in the repository root).
The vendored Nodz editor keeps its own MIT licence
(`glados_pycromanager/GUI/nodz/LICENSE.txt`).
