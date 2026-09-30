"""Typed exceptions for Glados-PycroManager.

Introduced by Phase 10 of the optimization plan. These types replace
bare ``except:`` swallowing and broad ``except Exception`` re-raises at
module boundaries. Each type carries a clear domain meaning so callers
can react (or fail loudly) rather than guessing.

Catch-all base: :class:`GladosError`. All subclasses inherit from it so
``except GladosError`` is a clean "anything from our code" filter.
"""

from __future__ import annotations


class GladosError(Exception):
    """Base class for every typed exception raised by this package."""


class BackendError(GladosError):
    """A Micro-Manager / Pycromanager / MMCore-Plus backend call failed.

    Raised by :class:`~glados_pycromanager.Core.microscopeInterfaceLayer.MicroscopeInterfaceLayer`
    helpers and other code crossing the Java / Python / C++ bridge. The
    original exception is chained via ``raise BackendError(...) from exc``.
    """


class ConfigError(GladosError):
    """A persisted configuration could not be parsed or validated.

    Covers the ``glados_state.json`` round-trip in
    :mod:`glados_pycromanager.io.appdata`: malformed JSON, missing
    schema-version field, or a version newer than this build understands.
    """


class RecipeError(GladosError):
    """An autonomous-microscopy recipe JSON failed validation.

    Raised by :mod:`glados_pycromanager.autonomous.recipe_io` on missing
    region keys, unknown schema version, or dangling node-id references.
    """


class NodeLoadError(GladosError):
    """A plugin node module is present but cannot be registered.

    Raised by :mod:`glados_pycromanager.plugins.discovery` when a dropped-in
    ``.py`` is missing ``__function_metadata__`` or the metadata does not
    name a callable on the module.
    """


class NodeDispatchError(GladosError):
    """The autonomous-microscopy registry was asked to dispatch a
    function name that is not registered.

    Raised by :func:`glados_pycromanager.autonomous.registry.dispatch`.
    """


class MDAEventError(GladosError):
    """The MDA event-list builder rejected an impossible plan.

    Raised by :mod:`glados_pycromanager.Core.MDAGlados` /
    ``MIL.create_mda`` on negative frame counts, unknown channel groups,
    zero-step z-stacks with non-zero range, or the mutually-exclusive
    default-argument trap captured in ``tests/test_mda_event_builder.py``.
    """


__all__ = [
    "GladosError",
    "BackendError",
    "ConfigError",
    "RecipeError",
    "NodeLoadError",
    "NodeDispatchError",
    "MDAEventError",
]
