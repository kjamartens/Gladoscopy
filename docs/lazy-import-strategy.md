# Deferred Heavy-Import Strategy for Autonomous Microscopy Nodes

## Why this matters

Node files in `Analysis_Measurements/`, `Real_Time_Analysis/`, and
`CustomFunctions/` are imported at application startup via the package
`__init__.py` discovery mechanism.  If a node file has a top-level import of a
heavy library (`bioimageio`, `diplib`, `stardist`, `csbdeep`, `cv2`, …), that
library is loaded during the startup scan — before the user has even opened the
autonomous-microscopy dock.  This adds 10–45 s to cold startup time and
increases memory pressure for libraries the user may never invoke.

Startup profiling (see `docs/perf-baseline.txt`) measured:

| Library           | Cumulative import cost |
|-------------------|----------------------:|
| bioimageio.core   | ~11 s                 |
| Real_Time_Analysis package | ~14 s (dominated by bioimageio) |
| CustomFunctions package    | ~4 s (dominated by csbdeep/cv2) |

## The contract

### Rule 1 — No heavy deps at module scope in node files

A "heavy dep" is any library that is not in the Python standard library and
takes > ~500 ms to import cold.  Known offenders in this codebase:

| Library                    | Where used                        |
|----------------------------|-----------------------------------|
| `bioimageio.core`          | `BioImageModelZoo.py`            |
| `bioimageio.spec`          | `BioImageModelZoo.py`            |
| `diplib`                   | `FFT_im.py`                      |
| `csbdeep`                  | `StarDist_image.py`              |
| `stardist`                 | `StarDist_image.py`              |
| `cv2` (opencv-python)      | `AutoFocusBF.py`                 |
| `tensorflow` / `keras`     | not currently at module scope    |

Standard scientific libs (`numpy`, base `scipy` / `scipy.ndimage`) are already paid
for by napari at startup — they are exempt. These are **not** (measured 2026-10-13):

- **`scipy.signal`** drags in `scipy.stats`, ~1 s. Import it inside the function.
- **`dask.array`, `pandas`, `ndtiff`, `pycromanager`**: `dask.array` (with xarray and
  pandas) is ~1 s after napari, and `ndtiff` and `pycromanager` both import it;
  `pycromanager` costs ~2.7 s in all. A PyMMCorePlus session never needs any of them
  at startup (L2.3, −1.9 s). Import them inside the function. For `ndtiff.NDTiffDataset`
  as a *type tag* (node metadata, port types), use
  `from glados_pycromanager.lazy_imports import ndtiff`: plugin discovery calls every
  node's `__function_metadata__()` at startup, and the tag compares, hashes and
  `isinstance`-checks like the real class without importing ndtiff.

**Module-scope *calls* count too.** A function called at import time that imports a
heavy library is a heavy import. `BioImageModelZoo.py` ran three bioimageio
compatibility patches at module scope; they imported `bioimageio.spec`,
`bioimageio.core` and torch, which made them the largest single cost of a warm start.
They now run from `_ensure_bioimageio_patched()` on first use.
`tests/test_node_packages_import_light.py` imports the three node packages in a fresh
interpreter and fails if any of these libraries appears.

### Rule 2 — Where to put the deferred import

The import must happen **before the library is first called**, but **not** on
every per-frame call:

#### Class-based RT nodes (have `__init__` / `run` / `end`)

```python
class MyNode:
    def __init__(self, core, **kwargs):
        logging.info("Loading MyHeavyLib (first use — may take a few seconds)…")
        import myheavylib
        self._lib = myheavylib           # store on self so run() can reach it
        # … rest of init …

    def run(self, image, metadata, shared_data, core, **kwargs):
        result = self._lib.do_work(image)   # NO import here — use self._lib
```

`__init__` is called once per autonomous-microscopy run when the user clicks
**Run** (before any frame is acquired).  The user-visible pause is acceptable
there; it would be invisible on a per-frame `run()` call.

#### Function-based analysis / custom nodes (no class, called once per scoring round)

```python
@register("Module.function")
def my_node(core, **kwargs):
    logging.info("Loading MyHeavyLib (first use — may take a few seconds)…")
    from myheavylib import useful_name   # cached in sys.modules after first call
    result = useful_name(kwargs["Image"])
    return result
```

Python's `sys.modules` cache means every call after the first is free.  The
first call pays the import cost, but that first call happens during the scoring
phase before acquisition starts — not mid-acquisition.

### Rule 3 — Always emit a `logging.info` message first

The line immediately before every deferred heavy import must be:

```python
logging.info("Loading <library> for <NodeName> (first use — may take a few seconds)…")
```

This message appears in the terminal / rotating log file so the user can see
that the pause is expected, not a hang.

**Future enhancement:** once the napari viewer reference is reliably available
to node `__init__`, replace with
`viewer.status = "Loading <library>…"` so the message surfaces in the napari
status bar without requiring the log file.

### Rule 4 — Remove dead imports immediately

If a node file imports a heavy library that it never actually calls (e.g.
`from csbdeep.utils import normalize` in `ExampleCustomFunction_DiceRoll.py`),
remove the import outright.

## Verification checklist

After applying this strategy, run:

```
grep -rn "^import bioimageio\|^from bioimageio\|^import diplib\|^import csbdeep\|^from csbdeep\|^import stardist\|^from stardist\|^import cv2\|^import tensorflow\|^from tensorflow" \
    glados_pycromanager/AutonomousMicroscopy \
    --include="*.py"
```

The output must be **empty**.  Any match is a regression.
