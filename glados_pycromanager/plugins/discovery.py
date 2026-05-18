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

from glados_pycromanager.errors import NodeLoadError

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
    """Return every `.py` in `folder` that isn't `__init__.py` or a dir.

    A missing or unreadable folder logs a single warning and returns
    an empty list — the AppData plugin walk must not bring the app
    down because the user's home folder has odd permissions.
    """
    if not folder.exists():
        logger.debug("Plugin folder %s does not exist; skipping", folder)
        return []
    if not folder.is_dir():
        logger.warning("Plugin path %s is not a directory; skipping", folder)
        return []
    try:
        entries = sorted(folder.iterdir())
    except (PermissionError, OSError) as exc:
        logger.warning("Plugin folder %s is unreadable: %s", folder, exc)
        return []
    out: list[Path] = []
    for entry in entries:
        if entry.name == "__init__.py":
            continue
        if entry.suffix != ".py":
            continue
        try:
            if not entry.is_file():
                continue
        except OSError as exc:
            logger.warning("Plugin entry %s is unstatable: %s", entry, exc)
            continue
        out.append(entry)
    return out


def _import_from_path(qualname: str, path: Path) -> ModuleType:
    """Import a single `.py` via `importlib.util.spec_from_file_location`."""
    spec = importlib.util.spec_from_file_location(qualname, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build spec for {path}")
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules *before* exec_module so that:
    # (a) circular imports within the plugin resolve correctly, and
    # (b) subsequent sys.modules lookups (e.g. subfunction_exists) find the
    #     already-loaded module and skip re-execution — preventing @register
    #     decorators from firing a second time.
    import sys as _sys
    _sys.modules[qualname] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        _sys.modules.pop(qualname, None)
        raise
    return module


def validate_node_module(module: ModuleType) -> None:
    """Verify a plugin module's ``__function_metadata__`` is well-formed.

    A node module is *expected* to expose a callable ``__function_metadata__``
    that returns a dict whose top-level keys are function names defined
    on the module. If the attribute is **absent**, the module is treated
    as a non-node helper and accepted silently — some legacy ``MainScripts/``
    files in these folders are not nodes. If the attribute is **present**
    but malformed, this raises :class:`~glados_pycromanager.errors.NodeLoadError`.

    Checks:
      - ``__function_metadata__`` is callable.
      - Calling it returns a ``dict``.
      - Each top-level key is a non-empty string.
      - Each value is itself a ``dict`` (the per-function metadata dict).
      - For each key, an attribute of the same name exists on the module
        and is callable — i.e. the metadata names a function that exists.

    Raises:
        NodeLoadError: With a message naming the module and the first
            failure detected.
    """
    meta_fn = getattr(module, "__function_metadata__", None)
    if meta_fn is None:
        return  # helper module, not a node — silently accepted

    if not callable(meta_fn):
        raise NodeLoadError(
            f"{module.__name__}: __function_metadata__ exists but is not callable"
        )

    try:
        meta = meta_fn()
    except Exception as exc:  # noqa: BLE001 — surface as NodeLoadError
        raise NodeLoadError(
            f"{module.__name__}: __function_metadata__() raised: {exc!r}"
        ) from exc

    if not isinstance(meta, dict):
        raise NodeLoadError(
            f"{module.__name__}: __function_metadata__() must return a dict, "
            f"got {type(meta).__name__}"
        )

    for fn_name, fn_meta in meta.items():
        if not isinstance(fn_name, str) or not fn_name:
            raise NodeLoadError(
                f"{module.__name__}: __function_metadata__ key {fn_name!r} "
                f"is not a non-empty string"
            )
        if not isinstance(fn_meta, dict):
            raise NodeLoadError(
                f"{module.__name__}: metadata entry for {fn_name!r} must be a "
                f"dict, got {type(fn_meta).__name__}"
            )
        attr = getattr(module, fn_name, None)
        if attr is None:
            raise NodeLoadError(
                f"{module.__name__}: metadata names {fn_name!r} but the "
                f"module has no such attribute"
            )
        if not callable(attr):
            raise NodeLoadError(
                f"{module.__name__}: {fn_name!r} exists but is not callable"
            )


def load_node_modules(
    folder: str | os.PathLike,
    prefix: str = "",
    *,
    use_package_import: bool = False,
    validate: bool = True,
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
        validate: When `True` (default), each successfully imported
            module is passed through :func:`validate_node_module`. A
            module that fails validation is reported in `failures`
            (with a :class:`NodeLoadError`) and excluded from
            `successes`. Set to `False` to skip validation, e.g. for
            test fixtures that intentionally ship without metadata.

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

        if validate:
            try:
                validate_node_module(module)
            except NodeLoadError as err:
                failures.append(
                    PluginLoadFailure(module_name=stem, path=path, error=err)
                )
                continue

        successes.append(module)

    return successes, failures


def user_appdata_dir_for(subfolder_pair: tuple[str, str]) -> Path:
    """`<appdirs.user_data_dir>/Glados-PycroManager/<first>/<second>`.

    The pair is `(parent_subpackage, leaf_subpackage)` — e.g.
    `("AutonomousMicroscopy", "Analysis_Measurements")`. Creates the
    directory if it doesn't exist so first-run can drop a `.py` into
    a known path.

    Tolerant of permission / I/O failures: logs a warning and returns
    the (still meaningful) path. Callers route through
    :func:`load_node_modules` which itself tolerates a missing folder.
    """
    parent, leaf = subfolder_pair
    root = Path(appdirs.user_data_dir()) / "Glados-PycroManager" / parent / leaf
    try:
        root.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as exc:
        logger.warning("Could not create AppData plugin dir %s: %s", root, exc)
    return root


def log_failures(failures: list[PluginLoadFailure]) -> None:
    """Emit a `warning` log line per failure. Phase 6.5 hookup."""
    for f in failures:
        logger.warning("Plugin load failed: %s", f)


_NODE_PACKAGES = [
    "glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements",
    "glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis",
    "glados_pycromanager.AutonomousMicroscopy.CustomFunctions",
]


def reload_all_node_modules() -> tuple[int, list[PluginLoadFailure]]:
    """Re-import every node `.py` from source trees and AppData directories.

    Designed for **developer hot-swap**: after editing or adding a node
    file, call this to pick up the latest version without restarting the
    app. Clears the function registry first so stale registrations from
    removed or renamed nodes are cleaned up.

    Returns:
        ``(success_count, failures)`` — number of successfully (re)loaded
        modules and a list of :class:`PluginLoadFailure` objects for any
        that errored.
    """
    import sys

    from glados_pycromanager.autonomous.registry import _REGISTRY

    # Wipe old registrations so deleted/renamed nodes don't linger.
    _REGISTRY.clear()
    logger.info("Registry cleared; reloading all node modules…")

    total_successes = 0
    all_failures: list[PluginLoadFailure] = []

    for pkg_name in _NODE_PACKAGES:
        pkg = sys.modules.get(pkg_name)
        if pkg is None:
            logger.debug("Node package not yet imported, skipping: %s", pkg_name)
            continue

        # Drop every sub-module from sys.modules so _import_from_path
        # re-executes the file (picks up edits, new files, deletions).
        prefix = pkg_name + "."
        for key in [k for k in list(sys.modules) if k.startswith(prefix)]:
            del sys.modules[key]

        # Reset package-level bookkeeping so _register() and _load_appdata()
        # behave as if the package is being imported for the first time.
        pkg.__all__ = []
        pkg._appdata_loaded = False

        # Re-load source-tree modules.
        source_dir = getattr(pkg, "_SOURCE_DIR", None)
        if source_dir:
            mods, failures = load_node_modules(source_dir, prefix=pkg_name)
            pkg._register(mods)
            log_failures(failures)
            total_successes += len(mods)
            all_failures.extend(failures)

        # Re-load AppData drop-in modules.
        appdata_dir = getattr(pkg, "_APPDATA_DIR", None)
        if appdata_dir:
            a_mods, a_failures = load_node_modules(appdata_dir, prefix=f"{pkg_name}.appdata")
            pkg._register(a_mods)
            log_failures(a_failures)
            total_successes += len(a_mods)
            all_failures.extend(a_failures)
            pkg._appdata_loaded = True

    logger.info(
        "Node reload complete: %d module(s) loaded, %d failure(s)",
        total_successes,
        len(all_failures),
    )
    return total_successes, all_failures
