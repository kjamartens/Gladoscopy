"""Phase 10.12 — registry.dispatch raises typed NodeDispatchError.

The registry's :class:`NodeDispatchError` now resolves to the typed
exception in :mod:`glados_pycromanager.errors`, which subclasses
:class:`GladosError`. Existing code that catches the registry symbol
keeps working — but the typed import path is now authoritative.
"""

from __future__ import annotations

import pytest

from glados_pycromanager.autonomous import registry
from glados_pycromanager.autonomous.registry import (
    dispatch,
    is_registered,
    register,
)
from glados_pycromanager.errors import GladosError, NodeDispatchError


def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the module-global registry with a fresh dict for this test."""
    monkeypatch.setattr(registry, "_REGISTRY", {})


def test_registry_exception_is_typed_glados_error() -> None:
    """The registry's NodeDispatchError is the same class as errors.NodeDispatchError."""
    assert registry.NodeDispatchError is NodeDispatchError
    assert issubclass(registry.NodeDispatchError, GladosError)


def test_dispatch_unknown_name_raises_node_dispatch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolated_registry(monkeypatch)
    with pytest.raises(NodeDispatchError, match="nope"):
        dispatch("nope")


def test_dispatch_unknown_name_also_caught_as_glados_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolated_registry(monkeypatch)
    with pytest.raises(GladosError):
        dispatch("absent.function")


def test_dispatch_known_function_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolated_registry(monkeypatch)

    @register("Module.do")
    def do(a: int, b: int) -> int:
        return a + b

    assert dispatch("Module.do", 2, 3) == 5
    assert is_registered("Module.do") is True


def test_dispatch_propagates_function_typeerror_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrong arity at the call site surfaces as Python's TypeError —
    that is the registered function's own contract and is not wrapped."""
    _isolated_registry(monkeypatch)

    @register("Module.needs_two")
    def needs_two(a: int, b: int) -> int:
        return a + b

    with pytest.raises(TypeError):
        dispatch("Module.needs_two", 1)  # missing b


def test_get_unknown_name_raises_node_dispatch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolated_registry(monkeypatch)
    with pytest.raises(NodeDispatchError):
        registry.get("nothing")
