"""Sanity checks for ``glados_pycromanager.errors``.

The module itself is data-only (just exception classes) but the tests
lock in the inheritance shape so downstream ``except`` blocks can rely
on it: every typed error inherits from ``GladosError`` and from
``Exception``.
"""

from __future__ import annotations

import pytest

from glados_pycromanager.errors import (
    BackendError,
    ConfigError,
    GladosError,
    MDAEventError,
    NodeDispatchError,
    NodeLoadError,
    RecipeError,
)


@pytest.mark.parametrize(
    "exc_type",
    [
        BackendError,
        ConfigError,
        RecipeError,
        NodeLoadError,
        NodeDispatchError,
        MDAEventError,
    ],
)
def test_inherits_from_glados_error(exc_type: type[Exception]) -> None:
    assert issubclass(exc_type, GladosError)
    assert issubclass(exc_type, Exception)


def test_glados_error_is_catchable_as_exception() -> None:
    with pytest.raises(GladosError):
        raise BackendError("boom")
    with pytest.raises(Exception):
        raise RecipeError("nope")


def test_chained_exception_preserved() -> None:
    """``raise ... from exc`` preserves the cause for diagnostics."""
    cause = RuntimeError("backend died")
    try:
        try:
            raise cause
        except RuntimeError as exc:
            raise BackendError("MIL.set_core") from exc
    except BackendError as final:
        assert final.__cause__ is cause
