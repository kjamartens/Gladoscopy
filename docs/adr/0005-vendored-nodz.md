# ADR 0005 — Vendored Nodz left untouched

* **Status**: Accepted (2026-05-17)

## Context

`glados_pycromanager/GUI/nodz/` is a fork of the Nodz node-graph
editor, vendored into the source tree. It is large
(`nodz_main.py` ~3 500 LOC), under-typed, contains its own `eval`
call site, and trips on most modern lint rules.

The 2026 optimization work (archived in `docs/plans/`) made many
sweeping changes: ruff auto-fix, mypy, refactor, error-handling
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
- Refactors, the eval → registry change, the error-handling and
  logging sweeps, and typing.
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

- The one `eval` in `nodz/nodz_main.py` (attribute loading) survives
  the registry change: it parses a dtype string from Nodz JSON. Threat model: same as
  recipe JSON (already untrusted-input-equivalent), so we accept it.
- The Nodz code uses old Qt patterns and bare `except:` blocks; those
  remain in our lint baseline but are silenced by the exclude.
- Tooltips attach metadata from outside Nodz so the "vendored /
  untouched" rule still holds.
- Exception (2026-10): the dead `nodz_custom.py` module, and the
  imports of the removed `HelperFunctions` module, were deleted from
  `nodz_main.py`. Neither came from upstream.

## Alternatives considered

1. **Re-write Nodz internals to match house style**. Reject: would
   make upstream sync impossible and adds an open-ended maintenance
   burden.
2. **Replace Nodz with another node-graph library**
   (NodeGraphQt, …). Possible long-term direction.
3. **Move Nodz to a real third-party install** (PyPI or git
   submodule). Reject for now: our fork has site-specific tweaks; the
   added install complexity isn't worth it.

## Related

- `docs/plans/claude_decisions.md`: `2026-05-17 — Vendored Nodz left alone`.
- `pyproject.toml` — ruff / mypy excludes.
- ADR 0002 — plugin discovery (the Nodz UI is how recipes are
  authored).
