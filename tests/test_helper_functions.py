"""
Unit tests for the autonomous-microscopy helper utilities.

Only the pure / side-effect-free helpers are covered — the metadata-reflection
helpers (kwargsFromFunction, infoFromMetadata, ...) rely on `eval()` against
modules dynamically loaded into globals at runtime and are not unit-testable
in isolation.

Phase 9.6 renamed ``createFunctionWith{Args,Kwargs}`` to
``..._str_for_display`` to signal that the result is no longer eval'd in
production. The original names are kept as DeprecationWarning aliases; we
test both the new canonical names and the alias contract here.
"""
import warnings

import pytest

from glados_pycromanager.AutonomousMicroscopy.MainScripts.HelperFunctions import (
    createFunctionWithArgs,
    createFunctionWithArgs_str_for_display,
    createFunctionWithKwargs,
    createFunctionWithKwargs_str_for_display,
    function_exists,
)


class TestFunctionExists:
    def test_regular_function_is_recognised(self):
        def some_fn():
            pass

        assert function_exists(some_fn) is True

    def test_lambda_is_recognised(self):
        # inspect.isfunction accepts lambdas too
        assert function_exists(lambda x: x) is True

    def test_builtin_is_rejected(self):
        # `len` is callable but not a Python-level function — the helper
        # specifically uses inspect.isfunction, so builtins must fail.
        assert function_exists(len) is False

    def test_non_callable_is_rejected(self):
        assert function_exists(42) is False
        assert function_exists("not callable") is False
        assert function_exists(None) is False

    def test_class_is_rejected(self):
        class Foo:
            pass

        # Classes are callable but not functions.
        assert function_exists(Foo) is False


class TestCreateFunctionWithArgsStrForDisplay:
    def test_no_args(self):
        # Builds "name.name()" — note the helper deliberately doubles the name.
        assert createFunctionWithArgs_str_for_display("foo") == "foo.foo()"

    def test_single_arg(self):
        assert createFunctionWithArgs_str_for_display("foo", "1") == "foo.foo(1)"

    def test_multiple_args_comma_separated(self):
        assert (
            createFunctionWithArgs_str_for_display("foo", "1", "'bar'", "3.14")
            == "foo.foo(1,'bar',3.14)"
        )

    def test_args_are_stringified(self):
        # The helper coerces each arg via str().
        assert createFunctionWithArgs_str_for_display("foo", 1, 2) == "foo.foo(1,2)"


class TestCreateFunctionWithKwargsStrForDisplay:
    def test_no_kwargs(self):
        assert createFunctionWithKwargs_str_for_display("foo") == "foo()"

    def test_single_kwarg(self):
        assert createFunctionWithKwargs_str_for_display("foo", x="1") == "foo(x=1)"

    def test_multiple_kwargs_comma_separated(self):
        # Python 3.7+ guarantees insertion order, so the call order matches the source order.
        out = createFunctionWithKwargs_str_for_display("foo", x="1", y="'bar'")
        assert out == "foo(x=1,y='bar')"

    def test_kwargs_are_stringified(self):
        assert createFunctionWithKwargs_str_for_display("foo", n=42) == "foo(n=42)"


class TestDeprecatedAliases:
    def test_args_alias_warns_and_delegates(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = createFunctionWithArgs("foo", "1")
        assert result == "foo.foo(1)"
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_kwargs_alias_warns_and_delegates(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = createFunctionWithKwargs("foo", x="1")
        assert result == "foo(x=1)"
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
