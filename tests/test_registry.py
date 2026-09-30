"""Tests for `glados_pycromanager.autonomous.registry`.

Phase 9.1 introduced the registry; Phase 9.5 added the
`dispatch_from_eval_text` parser-based helper. These tests pin both
behaviours: registration round-trips, dispatch resolves through the
registry, unknown names raise `NodeDispatchError`, and re-registration
of the same source location is idempotent (test reloaders rely on
this).
"""
from __future__ import annotations

import pytest

from glados_pycromanager.autonomous import registry


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Snapshot/restore the registry around each test so test order doesn't matter."""
    snapshot = dict(registry._REGISTRY)
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(snapshot)


def test_register_then_dispatch_calls_through():
    calls = []

    @registry.register("test.adder")
    def _adder(a, b, *, scale=1):
        calls.append((a, b, scale))
        return (a + b) * scale

    assert registry.is_registered("test.adder")
    assert registry.dispatch("test.adder", 2, 3, scale=10) == 50
    assert calls == [(2, 3, 10)]


def test_dispatch_unknown_name_raises_node_dispatch_error():
    with pytest.raises(registry.NodeDispatchError):
        registry.dispatch("test.does_not_exist")


def test_get_unknown_name_raises():
    with pytest.raises(registry.NodeDispatchError):
        registry.get("test.also_missing")


def test_registered_names_returns_sorted():
    @registry.register("zzz.late")
    def _late():
        pass

    @registry.register("aaa.early")
    def _early():
        pass

    names = registry.registered_names()
    assert names == sorted(names)
    assert "aaa.early" in names
    assert "zzz.late" in names


def test_reregistration_same_callable_is_silent():
    @registry.register("test.idem")
    def _fn():
        return "ok"

    # Same callable, same name — must not raise.
    registry.register("test.idem")(_fn)
    assert registry.dispatch("test.idem") == "ok"


def test_reregistration_same_source_location_is_idempotent():
    """Simulate a test-runner reload: same module + qualname, different fn id."""
    def _build():
        def _fn():
            return "first"
        _fn.__module__ = "tests.test_registry"
        _fn.__qualname__ = "test_reregistration_same_source_location_is_idempotent.<locals>._fn"
        return _fn

    first = _build()
    second = _build()
    assert first is not second

    registry.register("test.reload")(first)
    # Same module + qualname → idempotent overwrite, no raise.
    registry.register("test.reload")(second)

    assert registry.dispatch("test.reload") == "first"


def test_reregistration_with_truly_different_callable_raises():
    @registry.register("test.conflict")
    def _a():
        return "a"

    def _b():
        return "b"

    _b.__module__ = "some.other.module"
    _b.__qualname__ = "Different._b"

    with pytest.raises(registry.NodeDispatchError):
        registry.register("test.conflict")(_b)


# ---------------------------------------------------------------------
# dispatch_from_eval_text — Phase 9.5
# ---------------------------------------------------------------------


def test_dispatch_from_eval_text_no_args():
    @registry.register("EvalT.bare")
    def _bare():
        return "bare-output"

    assert registry.dispatch_from_eval_text("EvalT.bare()") == "bare-output"


def test_dispatch_from_eval_text_positional_args_resolved_from_scope():
    @registry.register("EvalT.summer")
    def _summer(a, b):
        return a + b

    scope = {"left": 10, "right": 32}
    assert registry.dispatch_from_eval_text("EvalT.summer(left, right)", scope=scope) == 42


def test_dispatch_from_eval_text_kwargs_resolved_from_scope():
    @registry.register("EvalT.kw")
    def _kw(*, label, count):
        return f"{label}:{count}"

    scope = {"the_label": "answer", "the_count": 42}
    result = registry.dispatch_from_eval_text(
        "EvalT.kw(label=the_label, count=the_count)",
        scope=scope,
    )
    assert result == "answer:42"


def test_dispatch_from_eval_text_attribute_chain_resolves():
    @registry.register("EvalT.attr")
    def _attr(core):
        return core["device"]

    class _SharedData:
        core = {"device": "FakeCam"}

    scope = {"self": type("S", (), {"shared_data": _SharedData()})()}
    result = registry.dispatch_from_eval_text(
        "EvalT.attr(self.shared_data.core)",
        scope=scope,
    )
    assert result == "FakeCam"


def test_dispatch_from_eval_text_unknown_function_raises():
    with pytest.raises(registry.NodeDispatchError):
        registry.dispatch_from_eval_text("EvalT.nope()")


def test_dispatch_from_eval_text_rejects_non_call_expression():
    with pytest.raises(ValueError, match="Call expression"):
        registry.dispatch_from_eval_text("1 + 2")


def test_dispatch_from_eval_text_rejects_syntax_error():
    with pytest.raises(ValueError, match="could not parse"):
        registry.dispatch_from_eval_text("not a (((")


def test_dispatch_from_eval_text_constants_work():
    @registry.register("EvalT.const")
    def _const(value, *, factor):
        return value * factor

    assert registry.dispatch_from_eval_text("EvalT.const(7, factor=6)") == 42
