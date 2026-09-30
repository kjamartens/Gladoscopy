"""T-F9: every napari mutation must reach the viewer on the GUI thread.

Threading invariant 3. `autonomous/executor.py` iterated `napariViewer.layers` and
called `layers.remove()` / `add_points()` / `add_shapes()` / `add_image()` from a
`QRunnable` on the thread pool; `utils.forceReset` set `shared_data.liveMode` from
a `ThreadPoolExecutor` thread, which re-enters `acqModeChanged` and reaches
`moveLayerToTop`; and `acqModeChanged` itself runs on the acquisition worker's
thread. That is the classic source of "layer list is inconsistent" errors and
vispy segfaults.

These tests exercise `NapariBridge` from real worker threads with a real
`QApplication` event loop, and check the migrated call sites route through it.
"""
from __future__ import annotations

import inspect
import os
import threading

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def bridge_mod(qapp):
    from glados_pycromanager.GUI import napari_bridge

    return napari_bridge


class _FakeLayer:
    def __init__(self, name):
        self.name = name


class _FakeLayers(list):
    def remove(self, layer):
        super().remove(layer)


class _FakeViewer:
    """Records which thread each mutation happened on."""

    def __init__(self):
        self.layers = _FakeLayers()
        self.threads = []
        self.dims = self

    def _record(self):
        self.threads.append(threading.current_thread().name)

    def add_image(self, **kwargs):
        self._record()
        layer = _FakeLayer(kwargs.get("name"))
        layer.kind = "image"
        layer.kwargs = kwargs
        self.layers.append(layer)
        return layer

    def add_points(self, **kwargs):
        self._record()
        layer = _FakeLayer(kwargs.get("name"))
        layer.kind = "points"
        layer.kwargs = kwargs
        self.layers.append(layer)
        return layer

    def add_shapes(self, **kwargs):
        self._record()
        layer = _FakeLayer(kwargs.get("name"))
        layer.kind = "shapes"
        layer.kwargs = kwargs
        self.layers.append(layer)
        return layer

    def set_current_step(self, axes, values):
        self._record()
        self.steps = (axes, values)


@pytest.fixture
def bridge(bridge_mod, qapp):
    viewer = _FakeViewer()
    return bridge_mod.NapariBridge(viewer), viewer


def _run_on_worker(fn, timeout=10):
    """Run `fn` on a plain thread while pumping the GUI event loop here."""
    from PyQt5.QtCore import QCoreApplication, QElapsedTimer, QEventLoop

    box = {}

    def _target():
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 -- surfaced to the test
            box["error"] = exc

    worker = threading.Thread(target=_target, name="bridge-test-worker")
    worker.start()

    clock = QElapsedTimer()
    clock.start()
    while worker.is_alive() and clock.elapsed() < timeout * 1000:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 10)
    worker.join(timeout)

    if "error" in box:
        raise box["error"]
    return box.get("result")


# ---------------------------------------------------------------- affinity


def test_bridge_takes_gui_thread_affinity_wherever_it_is_built(bridge_mod, qapp):
    """A worker may be the one to construct it; it must still live on the GUI thread."""
    built = _run_on_worker(lambda: bridge_mod.NapariBridge(_FakeViewer()))
    assert built.thread() is qapp.thread()


def test_on_gui_thread_is_true_here_and_false_on_a_worker(bridge_mod, qapp):
    assert bridge_mod.NapariBridge.on_gui_thread() is True
    assert _run_on_worker(bridge_mod.NapariBridge.on_gui_thread) is False


# ---------------------------------------------------------------- marshalling


def test_a_worker_mutation_runs_on_the_gui_thread(bridge, qapp):
    br, viewer = bridge
    layer = _run_on_worker(lambda: br.add_layer("image", name="from-worker", data=None))

    assert layer is not None and layer.name == "from-worker"
    assert viewer.threads == ["MainThread"], (
        "the mutation must not happen on the calling worker thread"
    )


def test_a_gui_thread_call_runs_inline(bridge, qapp):
    br, viewer = bridge
    layer = br.add_layer("points", name="from-gui", data=None)
    assert layer.name == "from-gui"
    assert viewer.threads == ["MainThread"]


def test_blocking_submit_returns_the_result(bridge, qapp):
    br, viewer = bridge
    assert _run_on_worker(lambda: br.submit(lambda v: 21 * 2, wait=True)) == 42


def test_fire_and_forget_returns_none_but_still_runs(bridge, qapp):
    br, viewer = bridge

    done = threading.Event()

    def _fn(_viewer):
        viewer._record()
        done.set()

    assert _run_on_worker(lambda: br.submit(_fn, wait=False)) is None
    # The call is queued; pump until it lands.
    _run_on_worker(lambda: done.wait(5))
    assert viewer.threads == ["MainThread"]


def test_an_exception_is_re_raised_on_the_caller(bridge, qapp):
    br, _ = bridge

    def _boom(_viewer):
        raise ValueError("layer says no")

    with pytest.raises(ValueError, match="layer says no"):
        _run_on_worker(lambda: br.submit(_boom, wait=True))


def test_a_wedged_gui_thread_times_out_rather_than_hanging(bridge_mod, qapp):
    """No event loop is pumped here, so the queued call never runs."""
    br = bridge_mod.NapariBridge(_FakeViewer())

    box = {}

    def _target():
        try:
            br.submit(lambda v: None, wait=True, timeout=0.2)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    worker = threading.Thread(target=_target)
    worker.start()
    worker.join(5)

    assert not worker.is_alive(), "the worker must not block forever"
    assert isinstance(box.get("error"), TimeoutError)


# ------------------------------------------------------------ layer helpers


def test_replace_layer_removes_then_adds_atomically(bridge, qapp):
    br, viewer = bridge
    first = br.add_layer("image", name="overlay", data=None)
    assert viewer.layers == [first]

    second = br.replace_layer("image", name="overlay", data=None, colormap="magma")
    assert viewer.layers == [second], "the old layer is gone, exactly one remains"
    assert second is not first
    assert second.kwargs["colormap"] == "magma"


def test_replace_layer_is_one_gui_thread_call(bridge_mod):
    """Two hops would leave a window with neither the old nor the new layer."""
    source = inspect.getsource(bridge_mod.NapariBridge.replace_layer)
    assert source.count("self.submit(") == 1


def test_remove_layer_removes_every_match_and_tolerates_none(bridge, qapp):
    br, viewer = bridge
    br.add_layer("image", name="a", data=None)
    br.add_layer("image", name="a", data=None)
    br.add_layer("image", name="b", data=None)

    assert br.remove_layer("a", wait=True) == 2
    assert [layer.name for layer in viewer.layers] == ["b"]
    assert br.remove_layer("nothing-here", wait=True) == 0


def test_update_layer_sets_an_attribute_on_the_named_layer(bridge, qapp):
    br, viewer = bridge
    br.add_layer("image", name="target", data=None)
    assert br.update_layer("target", "opacity", 0.5, wait=True) is True
    assert viewer.layers[0].opacity == 0.5
    assert br.update_layer("absent", "opacity", 0.5, wait=True) is False


def test_set_dims_step_uses_the_batched_form(bridge, qapp):
    """T-E1: one set_current_step call, not one per axis."""
    br, viewer = bridge
    br.set_dims_step([0, 1], [3, 4], wait=True)
    assert viewer.steps == ([0, 1], [3, 4])


def test_move_to_top_does_not_raise_for_a_missing_layer(bridge, qapp):
    br, _ = bridge
    br.move_to_top("never-created", wait=True)


# ------------------------------------------------------------ get_bridge


def test_get_bridge_is_cached_per_shared_data(bridge_mod, qapp):
    shared = type("S", (), {})()
    shared.napariViewer = _FakeViewer()
    first = bridge_mod.get_bridge(shared)
    assert bridge_mod.get_bridge(shared) is first


def test_get_bridge_picks_up_a_viewer_set_later(bridge_mod, qapp):
    shared = type("S", (), {})()
    shared.napariViewer = None
    br = bridge_mod.get_bridge(shared)
    assert br.viewer is None

    viewer = _FakeViewer()
    shared.napariViewer = viewer
    assert bridge_mod.get_bridge(shared).viewer is viewer


def test_get_bridge_without_shared_data_is_none(bridge_mod):
    assert bridge_mod.get_bridge(None) is None


def test_get_bridge_is_safe_from_a_worker(bridge_mod, qapp):
    shared = type("S", (), {})()
    shared.napariViewer = _FakeViewer()
    br = _run_on_worker(lambda: bridge_mod.get_bridge(shared))
    assert br.thread() is qapp.thread()


# -------------------------------------------------------- the migrated sites


def test_executor_no_longer_mutates_layers_directly(qapp):
    import glados_pycromanager.autonomous.executor as executor

    source = inspect.getsource(executor)
    assert "napariViewer.layers.remove(" not in source
    assert "viewer.add_points(" not in source
    assert "viewer.add_shapes(" not in source
    assert "viewer.add_image(" not in source
    assert "_replace_visualisation_layer" in source


def test_executor_helper_dispatches_every_layer_type(qapp):
    import glados_pycromanager.autonomous.executor as executor

    shared = type("S", (), {})()
    shared.napariViewer = _FakeViewer()

    for kind in ("points", "shapes", "image"):
        layer = executor._replace_visualisation_layer(shared, kind, "vis-%s" % kind, "gray")
        assert layer is not None and layer.kind == kind


def test_executor_helper_survives_an_unknown_type_and_no_shared_data(qapp):
    import glados_pycromanager.autonomous.executor as executor

    shared = type("S", (), {})()
    shared.napariViewer = _FakeViewer()
    assert executor._replace_visualisation_layer(shared, "surface", "x", "gray") is None
    assert executor._replace_visualisation_layer(None, "image", "x", "gray") is None


def test_acq_mode_changed_moves_layers_through_the_bridge(qapp):
    import glados_pycromanager.GUI.napariGlados as napariGlados

    source = inspect.getsource(napariGlados.napariHandler.acqModeChanged)
    assert "moveLayerToTop(self.shared_data.napariViewer" not in "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "_napari_bridge().move_to_top(" in source


def test_force_reset_flips_modes_through_the_bridge(qapp):
    import glados_pycromanager.GUI.utils as utils

    source = inspect.getsource(utils.forceReset_actual)
    assert "bridge.submit(_apply, wait=True" in source
    assert "shared_data.liveMode = False" not in source, (
        "the bare assignment re-entered acqModeChanged off the GUI thread"
    )
