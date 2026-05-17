"""Auto-discover custom-function nodes. See `Analysis_Measurements/__init__.py`."""
from __future__ import annotations

import sys

from glados_pycromanager.plugins.discovery import (
    load_node_modules,
    log_failures,
    user_appdata_dir_for,
)

_NAME_PARTS = __name__.split(".")
_HERE = (_NAME_PARTS[-2], _NAME_PARTS[-1])
_PKG = sys.modules[__name__]
_SOURCE_DIR = __spec__.submodule_search_locations[0] if __spec__ else None  # type: ignore[union-attr]

__all__: list[str] = []


def _register(modules) -> None:
    for mod in modules:
        stem = mod.__name__.rsplit(".", 1)[-1]
        setattr(_PKG, stem, mod)
        if stem not in __all__:
            __all__.append(stem)


_source_mods, _source_failures = load_node_modules(_SOURCE_DIR, prefix=__name__)
_register(_source_mods)
log_failures(_source_failures)

_APPDATA_DIR = user_appdata_dir_for(_HERE)
_appdata_mods, _appdata_failures = load_node_modules(
    _APPDATA_DIR, prefix=f"{__name__}.appdata"
)
_register(_appdata_mods)
log_failures(_appdata_failures)
