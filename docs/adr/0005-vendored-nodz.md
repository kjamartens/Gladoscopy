# ADR 0005 — Vendored Nodz left untouched

* **Status**: Accepted (2026-05-17)

## Context

`glados_pycromanager/GUI/nodz/` is a fork of the Nodz node-graph
editor, vendored into the source tree. It is large
(`nodz_main.py` ~3 500 LOC), under-typed, contains its own `eval`
call site, and trips on most modern lint rules.

The active optimization plan (`claude_project.md`) does many
sweeping changes — ruff auto-fix, mypy, refactor, error-handling
tightening. Without a clear policy, those sweeps would also rewrite
Nodz internals, which would (a) make it impossible to re-sync with
the upstream Nodz repo and (b) burn cycles on code we don't intend to
own.

## Decision

`glados_pycromanager/GUI/nodz/` is treated as **third-party** and is
excluded from:

- `ruff` (auto-fix, format, check) — `tool.ruff.extend-exclude`.
- `mypy` — `tool.mypy.exclude`.
- `bandit` — `--exclude` on the CLI.
- `pre-commit` hooks (whitespace, end-of-file, mixed line ending) —
  per-hook `exclude:` regex.
- Phase 7 (split god-files in `utils.py`), Phase 8 (split
  `FlowChart_dockWidgets.py`), Phase 9 (eval → registry),
  Phase 10 (error-handling sweep), Phase 11 (logging unification),
  Phase 15 (typing).
- The module map (`docs/module-map.md`) lists it as "vendored, see
  upstream" rather than enumerating internals.

The Nodz folder still ships in the wheel via the
`tool.setuptools.package-data` entry.

## Consequences

**Positive**

- We can pull in upstream Nodz changes by diffing
  `glados_pycromanager/GUI/nodz/` against the upstream commit without
  fighting our own formatting / type churn.
- Lint / mypy noise drops dramatically.

**Negative**

- The one `eval` in `nodz/nodz_main.py:1493` survives Phase 9 — it
  parses a dtype string from Nodz JSON. Threat model: same as
  recipe JSON (already untrusted-input-equivalent), so we accept it.
- The Nodz code uses old Qt patterns and bare `except:` blocks; those
  remain in our lint baseline but are silenced by the exclude.
- Tooltips added in Phase 14.4 attach metadata from outside Nodz so
  the "vendored / untouched" rule still holds.

## Alternatives considered

1. **Re-write Nodz internals to match house style**. Reject: would
   make upstream sync impossible and adds an open-ended maintenance
   burden.
2. **Replace Nodz with another node-graph library**
   (NodeGraphQt, …). Possible long-term direction; out of scope for
   this optimization plan.
3. **Move Nodz to a real third-party install** (PyPI or git
   submodule). Reject for now: our fork has site-specific tweaks; the
   added install complexity isn't worth it.

## Related

- `claude_decisions.md` — `2026-05-17 — Vendored Nodz left alone`.
- `pyproject.toml` — ruff / mypy excludes.
- ADR 0002 — plugin discovery (the Nodz UI is how recipes are
  authored).
