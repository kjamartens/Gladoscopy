"""Load autonomous-microscopy node modules from a folder.

The autonomous engine's three subpackages
(`Analysis_Measurements/`, `Real_Time_Analysis/`, `CustomFunctions/`)
used to do this work inline in their `__init__.py` — walking the
source folder, walking the user's AppData folder, `exec()`-ing
`from .X import *`, and silently swallowing import errors. That made
discovery untestable and bugs invisible.

This module centralises the loader. `load_node_modules(folder, prefix)`
returns a list of imported `ModuleType` objects and a parallel list of
load failures so the caller can decide what to do with each. The
package `__init__.py` files use it twice: once for the source folder,
once for the AppData folder.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import appdirs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginLoadFailure:
    """One entry in `load_node_modules`'s `failures` return list."""

    module_name: str
    path: Path
    error: BaseException

    def __str__(self) -> str:  # pragma: no cover — convenience for logs
        return f"{self.module_name} ({self.path}): {self.error!r}"


def _iter_module_files(folder: Path) -> list[Path]:
    """Return every `.py` in `folder` that isn't `__init__.py` or a dir."""
    if not folder.is_dir():
        return []
    out: list[Path] = []
    for entry in sorted(folder.iterdir()):
        if entry.name == "__init__.py":
            continue
        if entry.suffix != ".py":
            continue
        if not entry.is_file():
            continue
        out.append(entry)
    return out


def _import_from_path(qualname: str, path: Path) -> ModuleType:
    """Import a single `.py` via `importlib.util.spec_from_file_location`."""
    spec = importlib.util.spec_from_file_location(qualname, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_node_modules(
    folder: str | os.PathLike,
    prefix: str = "",
    *,
    use_package_import: bool = False,
) -> tuple[list[ModuleType], list[PluginLoadFailure]]:
    """Import every node `.py` in `folder` and return them.

    Args:
        folder: Directory holding `<NodeName>.py` files.
        prefix: Dotted prefix attached to each module's qualified name.
            For source-tree calls this should be the calling package's
            `__name__`; for AppData calls it's typically
            `"<package>.appdata"`. Pass `""` for ad-hoc loads (tests).
        use_package_import: When `True`, use `importlib.import_module`
            against `<prefix>.<stem>` (only valid when `folder` is the
            real on-disk directory of the package whose `__name__`
            matches `prefix`). When `False` (default), every file is
            loaded via `spec_from_file_location` — works regardless of
            where the folder lives, which is the AppData case.

    Returns:
        `(modules, failures)`. `modules` is the list of successfully
        loaded module objects in directory-listing order; `failures`
        carries `(name, path, error)` triples for every file that
        failed to import. Callers should typically pass `failures` to
        `log_failures(...)` (Phase 6.5 wires this up).
    """
    base = Path(folder)
    successes: list[ModuleType] = []
    failures: list[PluginLoadFailure] = []

    for path in _iter_module_files(base):
        stem = path.stem
        qualname = f"{prefix}.{stem}" if prefix else stem
        try:
            if use_package_import and prefix:
                module = importlib.import_module(qualname)
            else:
                module = _import_from_path(qualname, path)
        except Exception as err:  # noqa: BLE001 — collect for the caller
            failures.append(PluginLoadFailure(module_name=stem, path=path, error=err))
            continue
        successes.append(module)

    return successes, failures


def user_appdata_dir_for(subfolder_pair: tuple[str, str]) -> Path:
    """`<appdirs.user_data_dir>/Glados-PycroManager/<first>/<second>`.

    The pair is `(parent_subpackage, leaf_subpackage)` — e.g.
    `("AutonomousMicroscopy", "Analysis_Measurements")`. Creates the
    directory if it doesn't exist so first-run can drop a `.py` into
    a known path.
    """
    parent, leaf = subfolder_pair
    root = Path(appdirs.user_data_dir()) / "Glados-PycroManager" / parent / leaf
    root.mkdir(parents=True, exist_ok=True)
    return root


def log_failures(failures: list[PluginLoadFailure]) -> None:
    """Emit a `warning` log line per failure. Phase 6.5 hookup."""
    for f in failures:
        logger.warning("Plugin load failed: %s", f)
