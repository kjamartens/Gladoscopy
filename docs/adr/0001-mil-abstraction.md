# ADR 0001 — MicroscopeInterfaceLayer (MIL) as the single backend seam

* **Status**: Accepted (historical; ratified 2026-05-17)
* **Deciders**: Project maintainer (K. Martens)
* **Consulted**: This ADR is retroactive — the abstraction predates
  the optimization plan.

## Context

Glados-PycroManager has to talk to Micro-Manager through three
mutually-exclusive backends:

| Backend                  | Library                  | Notes                                 |
| ------------------------ | ------------------------ | ------------------------------------- |
| `PYCROMANAGER_JAVA`      | `pycromanager.Core`      | Requires running MM Java server :4827 |
| `PYCROMANAGER_PYTHON`    | `pycromanager` headless  | Pure-Python boot                      |
| `MMCORE_PLUS`            | `pymmcore-plus`          | Pure-Python CMMCore wrapper           |

Without a seam, every UI handler would carry `if backend == 'JAVA':
else if backend == 'PythonHeadless': ...` branches. The user picks one
backend at startup; that choice should be invisible to the rest of the
code.

## Decision

`Core/microscopeInterfaceLayer.py` defines
`MicroscopeInterfaceLayer` (alias **MIL**). Every other module that
needs Micro-Manager goes through MIL. The backend object lives in
`MIL._core`; `MIL.set_core(core)` is called once at startup with the
chosen backend's object. The `MicroscopeInstance` enum encodes which
of the three backends is active, and MIL methods branch on
`isinstance(self._core, ...)` checks.

## Consequences

**Positive**

- The rest of the codebase is backend-agnostic. Three backends ship.
- Single place to add new backends (`pymmcore-zmq`, …).
- Single place to fix backend-specific quirks (e.g. Java-bridge
  attribute resolution).

**Negative**

- `isinstance(...)` dispatch runs on every MIL call. Profile-relevant
  for hot paths; addressed by Phase 6.1 / PERF-4 of the optimization
  plan (cache `MicroscopeInstance` once in `set_core`).
- The MIL surface area is large (~50 public methods) and any new
  capability needs three implementations. We treat that as the cost of
  the abstraction.

## Alternatives considered

1. **Duck-typing** — Have UI code use the backend object directly and
   rely on Pycromanager and pymmcore-plus exposing the same methods.
   Rejected: the surface diverges enough (Java-bridge attribute
   resolution, header metadata format) that this would leak
   backend-specific branches into many call sites.
2. **Adapter pattern** — Pull each backend behind its own adapter
   class with a shared abstract base. The current MIL is morally that,
   but as a single class with branched bodies; splitting into adapter
   classes adds files without changing the seam. Could revisit if MIL
   grows past ~1 200 LOC.

## Related

- `docs/module-map.md` — MIL entry.
- `claude_project.md` — Phase 6.1 caches the backend tag.
- `tests/test_microscope_interface_layer.py` — covers backend
  detection.
