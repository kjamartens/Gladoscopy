"""Auto-discover analysis-measurement nodes.

Loads every `.py` in this directory and in the matching per-user
AppData folder, then exposes each as a package-level attribute. The
real work lives in `glados_pycromanager.plugins.discovery`; see ADR
0002 for the rationale.

Until Phase 6, the discovery logic was duplicated here, in
`Real_Time_Analysis/__init__.py`, and in `CustomFunctions/__init__.py`,
and used `exec()` + a silent `except ModuleNotFoundError`. Both are
now gone.
"""
from __future__ import annotations

import sys

from glados_pycromanager.plugins.discovery import (
    load_node_modules,
    log_failures,
    user_appdata_dir_for,
)

# `_HERE` is `("AutonomousMicroscopy", "Analysis_Measurements")` — the
# last two dotted segments of `__name__`. Used to compute the AppData
# subfolder so user-drop-ins land in the per-subpackage tree.
_NAME_PARTS = __name__.split(".")
_HERE = (_NAME_PARTS[-2], _NAME_PARTS[-1])
_PKG = sys.modules[__name__]
_SOURCE_DIR = __spec__.submodule_search_locations[0] if __spec__ else None  # type: ignore[union-attr]

__all__: list[str] = []


def _register(modules) -> None:
    """Bind each loaded module to this package and append its stem to __all__."""
    for mod in modules:
        stem = mod.__name__.rsplit(".", 1)[-1]
        setattr(_PKG, stem, mod)
        if stem not in __all__:
            __all__.append(stem)


# 1) Source-tree modules — defer attribute binding until after every
#    module has finished loading. That way an intra-load `from
#    glados_pycromanager.GUI.utils import *` (which itself
#    `from .AutonomousMicroscopy.Analysis_Measurements import *`s the
#    partially-loaded package) sees an empty `__all__` and is a no-op
#    instead of triggering circular-import AttributeError.
_source_mods, _source_failures = load_node_modules(_SOURCE_DIR, prefix=__name__)
_register(_source_mods)
log_failures(_source_failures)

# 2) AppData drop-ins — same contract, but under a synthetic
#    `<package>.appdata` qualname so source-tree and AppData modules
#    can't collide in `sys.modules`.
_APPDATA_DIR = user_appdata_dir_for(_HERE)
_appdata_loaded: bool = False


def _load_appdata() -> None:
    """Load user AppData drop-in modules. Called lazily when the autonomous dock is built."""
    global _appdata_loaded
    if _appdata_loaded:
        return
    _appdata_loaded = True
    _appdata_mods, _appdata_failures = load_node_modules(
        _APPDATA_DIR, prefix=f"{__name__}.appdata"
    )
    _register(_appdata_mods)
    log_failures(_appdata_failures)
