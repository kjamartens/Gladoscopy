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

import ast
from typing import Any, Callable, Mapping


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


def dispatch_from_eval_text(eval_text: str, scope: Mapping[str, Any] | None = None) -> Any:
    """Parse a ``Module.Function(args)`` source string and dispatch via the registry.

    Phase 9.5 replacement for the bare ``eval(eval_text)`` recipe-call
    pattern. The *function name* is resolved through :func:`dispatch` —
    unknown names raise :class:`NodeDispatchError` instead of executing
    arbitrary code at module scope. Argument expressions are still
    evaluated (in ``scope``) so identifier references like
    ``ImageData_3`` and attribute chains like ``self.shared_data.core``
    continue to resolve the way the legacy eval string did.

    This is a *partial* security improvement: argument expressions can
    still call functions present in ``scope``. A full mitigation would
    require a small recipe-expression language and is out of scope for
    Phase 9. Phase 10.6 will validate recipe schemas before dispatch.

    Args:
        eval_text: The recipe-built call expression, e.g.
            ``"AverageImage.AvgImage(self.shared_data.core, Image=ImageData_3)"``.
        scope: Mapping used as the globals/locals for argument-expression
            evaluation. Pass everything the legacy ``eval(eval_text)``
            could see (`self`, `core`, `shared_data`, the nodzVariable
            dict, plus the module globals if needed).

    Returns:
        The return value of the registered function.

    Raises:
        ValueError: If ``eval_text`` does not parse as a single call
            expression.
        NodeDispatchError: If the resolved function name is not in the
            registry.
    """
    try:
        tree = ast.parse(eval_text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(
            f"dispatch_from_eval_text could not parse {eval_text!r}: {exc}"
        ) from exc
    if not isinstance(tree.body, ast.Call):
        raise ValueError(
            f"dispatch_from_eval_text expected a Call expression, got {type(tree.body).__name__}"
        )
    call = tree.body
    func_name = ast.unparse(call.func)
    scope_dict: dict[str, Any] = dict(scope) if scope else {}
    args = [
        eval(compile(ast.Expression(a), "<dispatch-arg>", "eval"), scope_dict)
        for a in call.args
    ]
    kwargs = {
        kw.arg: eval(compile(ast.Expression(kw.value), "<dispatch-kw>", "eval"), scope_dict)
        for kw in call.keywords
        if kw.arg is not None
    }
    return dispatch(func_name, *args, **kwargs)


def _reset_for_tests() -> None:
    """Clear the registry. Test-only — never call from production code."""
    _REGISTRY.clear()
