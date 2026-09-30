"""Phase 10.5 — validate plugin __function_metadata__ on load.

A `.py` dropped into the AppData plugin folder gets imported by
`plugins.discovery.load_node_modules`. With ``validate=True``
(the default), each imported module is then checked against
:func:`plugins.discovery.validate_node_module`. Modules whose
metadata is malformed land in the *failures* list with a
:class:`NodeLoadError` and are excluded from ``successes`` —
they fail loudly rather than silently passing through.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from glados_pycromanager.errors import NodeLoadError
from glados_pycromanager.plugins.discovery import (
    load_node_modules,
    validate_node_module,
)


def _drop(folder: Path, name: str, body: str) -> Path:
    p = folder / f"{name}.py"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_valid_node_module_loads(tmp_path: Path) -> None:
    _drop(
        tmp_path,
        "GoodNode",
        """
        def __function_metadata__():
            return {"DoStuff": {"display_name": "Do Stuff"}}

        def DoStuff(core, **kwargs):
            return 42
        """,
    )

    successes, failures = load_node_modules(tmp_path, prefix="testpkg")
    assert failures == []
    assert len(successes) == 1
    assert successes[0].DoStuff(None) == 42


def test_helper_module_without_metadata_is_accepted(tmp_path: Path) -> None:
    """A `.py` without __function_metadata__ is treated as a non-node
    helper module (e.g. a `MainScripts` file) — silently accepted."""
    _drop(
        tmp_path,
        "HelperOnly",
        """
        def utility():
            return "helper"
        """,
    )
    successes, failures = load_node_modules(tmp_path, prefix="testpkg")
    assert failures == []
    assert len(successes) == 1


def test_metadata_not_callable_is_reported(tmp_path: Path) -> None:
    _drop(
        tmp_path,
        "BadMeta",
        """
        __function_metadata__ = {"oops": "should-be-callable"}
        """,
    )
    successes, failures = load_node_modules(tmp_path, prefix="testpkg")
    assert successes == []
    assert len(failures) == 1
    assert isinstance(failures[0].error, NodeLoadError)
    assert "not callable" in str(failures[0].error)


def test_metadata_returns_non_dict_is_reported(tmp_path: Path) -> None:
    _drop(
        tmp_path,
        "WrongShape",
        """
        def __function_metadata__():
            return ["a", "list", "is", "wrong"]

        def whatever(core, **kwargs):
            pass
        """,
    )
    successes, failures = load_node_modules(tmp_path, prefix="testpkg")
    assert successes == []
    assert len(failures) == 1
    assert isinstance(failures[0].error, NodeLoadError)
    assert "must return a dict" in str(failures[0].error)


def test_metadata_names_missing_function_is_reported(tmp_path: Path) -> None:
    _drop(
        tmp_path,
        "MissingFn",
        """
        def __function_metadata__():
            return {"NonExistent": {"display_name": "Phantom"}}
        """,
    )
    successes, failures = load_node_modules(tmp_path, prefix="testpkg")
    assert successes == []
    assert len(failures) == 1
    assert isinstance(failures[0].error, NodeLoadError)
    assert "NonExistent" in str(failures[0].error)


def test_metadata_entry_must_be_dict(tmp_path: Path) -> None:
    _drop(
        tmp_path,
        "BadEntry",
        """
        def __function_metadata__():
            return {"DoStuff": "not-a-dict"}

        def DoStuff(core, **kwargs):
            pass
        """,
    )
    successes, failures = load_node_modules(tmp_path, prefix="testpkg")
    assert successes == []
    assert len(failures) == 1
    assert isinstance(failures[0].error, NodeLoadError)


def test_metadata_function_present_but_not_callable(tmp_path: Path) -> None:
    _drop(
        tmp_path,
        "NotCallable",
        """
        DoStuff = 99   # exists on module but is not callable

        def __function_metadata__():
            return {"DoStuff": {}}
        """,
    )
    successes, failures = load_node_modules(tmp_path, prefix="testpkg")
    assert successes == []
    assert len(failures) == 1
    assert "not callable" in str(failures[0].error)


def test_metadata_call_raises_is_wrapped(tmp_path: Path) -> None:
    _drop(
        tmp_path,
        "Raiser",
        """
        def __function_metadata__():
            raise RuntimeError("boom")

        def DoStuff(core, **kwargs):
            pass
        """,
    )
    successes, failures = load_node_modules(tmp_path, prefix="testpkg")
    assert successes == []
    assert len(failures) == 1
    assert isinstance(failures[0].error, NodeLoadError)
    assert isinstance(failures[0].error.__cause__, RuntimeError)


def test_validate_can_be_disabled(tmp_path: Path) -> None:
    """`validate=False` short-circuits the metadata check — used by
    legacy tests / loaders that don't care about node contracts."""
    _drop(
        tmp_path,
        "BadEntry",
        """
        def __function_metadata__():
            return {"DoStuff": "not-a-dict"}

        def DoStuff(core, **kwargs):
            pass
        """,
    )
    successes, failures = load_node_modules(
        tmp_path, prefix="testpkg", validate=False
    )
    assert len(successes) == 1
    assert failures == []


def test_validate_node_module_directly_raises() -> None:
    """`validate_node_module` is also callable on its own and raises
    `NodeLoadError` for direct use by other validation tools."""
    import types

    mod = types.ModuleType("synthetic")
    mod.__function_metadata__ = lambda: {"Missing": {}}  # type: ignore[attr-defined]
    with pytest.raises(NodeLoadError, match="Missing"):
        validate_node_module(mod)
