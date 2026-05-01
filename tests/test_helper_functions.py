"""
Unit tests for the autonomous-microscopy helper utilities.

Only the pure / side-effect-free helpers are covered — the metadata-reflection
helpers (kwargsFromFunction, infoFromMetadata, ...) rely on `eval()` against
modules dynamically loaded into globals at runtime and are not unit-testable
in isolation.
"""
import pytest

from glados_pycromanager.AutonomousMicroscopy.MainScripts.HelperFunctions import (
    createFunctionWithArgs,
    createFunctionWithKwargs,
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


class TestCreateFunctionWithArgs:
    def test_no_args(self):
        # Builds "name.name()" — note the helper deliberately doubles the name.
        assert createFunctionWithArgs("foo") == "foo.foo()"

    def test_single_arg(self):
        assert createFunctionWithArgs("foo", "1") == "foo.foo(1)"

    def test_multiple_args_comma_separated(self):
        assert createFunctionWithArgs("foo", "1", "'bar'", "3.14") == "foo.foo(1,'bar',3.14)"

    def test_args_are_stringified(self):
        # The helper coerces each arg via str().
        assert createFunctionWithArgs("foo", 1, 2) == "foo.foo(1,2)"


class TestCreateFunctionWithKwargs:
    def test_no_kwargs(self):
        assert createFunctionWithKwargs("foo") == "foo()"

    def test_single_kwarg(self):
        assert createFunctionWithKwargs("foo", x="1") == "foo(x=1)"

    def test_multiple_kwargs_comma_separated(self):
        # Python 3.7+ guarantees insertion order, so the call order matches the source order.
        out = createFunctionWithKwargs("foo", x="1", y="'bar'")
        assert out == "foo(x=1,y='bar')"

    def test_kwargs_are_stringified(self):
        assert createFunctionWithKwargs("foo", n=42) == "foo(n=42)"
