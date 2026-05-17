# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — `claude_optimization` branch

Ongoing optimization driven by `claude_project.md`. See `claude_decisions.md`
for design rationale per step. Highlights so far:

### Security
- Removed stale hard-coded Slack token + signing secret from
  `WebhookConfig` defaults (the token was confirmed expired). Runtime
  values are now entered via the new **Slack settings…** dialog and
  persisted to per-user AppData. Cf. `SECURITY.md`.
- Baseline `bandit` scan checked in at `docs/bandit-baseline.txt`.
- `docs/eval-inventory.md` catalogs the ~63 `eval()` call sites for
  the Phase 9 registry replacement.

### Added
- `glados_pycromanager/GUI/slack_settings_dialog.py` — QDialog for
  entering Slack token/secret/channel at runtime; wired into the
  autonomous-microscopy dock toolbar.
- `tests/test_slack_settings_persistence.py` — round-trip the three
  fields through `save_config_to_json` / `load_config_from_json`.
- `_slack_send_enabled()` helper centralizes the empty-token guard so
  the two Slack-send call sites no-op (with an info log pointing at
  the dialog) when no credentials are set.
- `SECURITY.md`, `CONTRIBUTING.md`, this file.
- `docs/baseline.txt`, `docs/bandit-baseline.txt`, `docs/eval-inventory.md`.

### Tooling
- `ruff`, `mypy`, `pre-commit`, `Makefile`, `.github/workflows/ci.yml`
  — see `pyproject.toml`. Vendored Nodz excluded from all of them.
- Pytest now passes `-p no:napari -p no:npe2 -p no:napari_plugin_engine`
  in `addopts` (the auto-loaded plugins hang the suite via the project's
  own napari manifest).

### Fixed
- Two pre-existing typos at the Slack-send call sites
  (`webook_config` → `webhook_config`; `shared_dataconfig` →
  `shared_data.config`) that previously made the code crash on
  attribute access before the empty-token guard could fire.

### Build / packaging
- Dropped the leading-slash package-data globs (`"/*"`,
  `"/Documentation/*"`) — they silently included nothing and on
  Windows could trigger `Permission denied` against `C:\DumpStack.log`.
- Switched to `tool.setuptools.packages.find` for auto-discovery.

### Repo hygiene
- Untracked the two ~34 MB `scalene-profile.{html,json}` artifacts;
  history rewrite tracked under `HYG-3`.
- Moved `Test.py` / `test.ipynb` to `scratch/` (excluded from
  sdist/wheel).
- `.gitignore` adds `scalene-profile.*`, `*.docx`, `~$*`, `*.swp`,
  `bash.exe.stackdump`.

## [0.0.2] — earlier

The state of the project at the point the `claude_optimization` branch
was cut from `Code-cleanup`. No formal changelog existed prior; see
`git log main` for the historical record.
