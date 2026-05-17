"""Autonomous-microscopy function registry.

Phase 9 replaces the `eval(createFunctionWithKwargs(...))` recipe-dispatch
path with a registry lookup. Plugin modules under
`glados_pycromanager.AutonomousMicroscopy.{Analysis_Measurements,
Real_Time_Analysis,CustomFunctions}` decorate their callable functions
with ``@register("ModuleName.FunctionName")``. At runtime the executor
calls ``dispatch(name, *args, **kwargs)`` instead of building a Python
source string and eval'ing it.

The decorator is a no-op at call time — it just records the function in
the module-level ``_REGISTRY`` dict and returns it unchanged. Functions
remain importable / callable / testable in the usual way.

Phase 10.1 introduces a typed ``NodeDispatchError`` in
``glados_pycromanager.errors``; this module defines a local ``KeyError``
subclass with the same name so Phase 9 can land first and Phase 10.1
re-points the import without churn.
"""

from __future__ import annotations

from typing import Callable


class NodeDispatchError(KeyError):
    """Raised when ``dispatch()`` cannot resolve a node-function name.

    Subclasses ``KeyError`` so existing ``except KeyError`` blocks keep
    catching it. Phase 10.1 moves this exception into a dedicated
    ``glados_pycromanager.errors`` module.
    """


_REGISTRY: dict[str, Callable] = {}


def register(name: str) -> Callable[[Callable], Callable]:
    """Decorator: record ``fn`` under ``name`` in the global registry.

    Args:
        name: The dotted node-function name as used in recipe JSON and
            menu strings — typically ``"<module-stem>.<function>"``,
            e.g. ``"AverageImage.AvgImage"``.

    Returns:
        Identity decorator; the decorated function is unchanged.
    """

    def _decorator(fn: Callable) -> Callable:
        existing = _REGISTRY.get(name)
        if existing is not None and existing is not fn:
            # A different *callable* under the same name is almost always a
            # real conflict (duplicate decorator, AppData-dropped node
            # shadowing a built-in). But Python test reloaders re-execute
            # plugin modules, which produces a brand-new function object
            # for the same source location — that case is idempotent, not
            # a conflict.
            same_source = (
                getattr(existing, "__module__", None) == getattr(fn, "__module__", None)
                and getattr(existing, "__qualname__", None) == getattr(fn, "__qualname__", None)
            )
            if not same_source:
                raise NodeDispatchError(
                    f"Refusing to re-register node function {name!r}: "
                    f"existing {existing!r}, new {fn!r}"
                )
        _REGISTRY[name] = fn
        return fn

    return _decorator


def dispatch(name: str, *args, **kwargs):
    """Call the registered function ``name`` with the given arguments.

    Args:
        name: Dotted node-function name used at registration time.
        *args: Positional args forwarded to the function.
        **kwargs: Keyword args forwarded to the function.

    Raises:
        NodeDispatchError: If ``name`` is not in the registry.
    """
    try:
        fn = _REGISTRY[name]
    except KeyError as exc:
        raise NodeDispatchError(
            f"No node function registered as {name!r}. "
            f"Known: {sorted(_REGISTRY)[:8]}..."
        ) from exc
    return fn(*args, **kwargs)


def is_registered(name: str) -> bool:
    """Return True if ``name`` resolves to a registered function."""
    return name in _REGISTRY


def registered_names() -> list[str]:
    """Return all registered names, sorted for stable iteration."""
    return sorted(_REGISTRY)


def get(name: str) -> Callable:
    """Return the registered callable for ``name`` without invoking it.

    Raises:
        NodeDispatchError: If ``name`` is not in the registry.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise NodeDispatchError(
            f"No node function registered as {name!r}"
        ) from exc


def _reset_for_tests() -> None:
    """Clear the registry. Test-only — never call from production code."""
    _REGISTRY.clear()
