# .claude/commands — slash command home

This directory hosts user-facing slash commands for Claude Code. The
contents will be authored in **Phase 16** of `claude_project.md`. Until
then this README is a placeholder so the directory exists in git.

Planned commands:

- `run-tests.md` — invoke `pytest -q` against the suite.
- `lint.md` — run `ruff check` + `mypy` (config from `pyproject.toml`).
- `profile-startup.md` — wrap `python -X importtime` against the
  `glados_pycromanager` package and dump the timing to
  `docs/perf-baseline.txt`.
- `new-node.md` — scaffold a new autonomous-microscopy node from a
  template (asks for type — analysis / real-time / custom — and name).

When a `.md` is added here it becomes available as `/name` inside Claude
Code.
