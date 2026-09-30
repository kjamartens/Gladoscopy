"""T-F9: a GUI-thread owner for every napari mutation.

Threading invariant 3 of `claude_throughput_project.md`: *only the GUI thread
touches napari*. Workers emit; a GUI-thread receiver mutates. Several places did
not follow it -- `autonomous/executor.py` added and removed layers from a
`QRunnable` on the thread pool, `utils.forceReset` reached `moveLayerToTop` from a
`ThreadPoolExecutor` thread, and `napariHandler.acqModeChanged` runs on the
acquisition worker's own thread. That is the classic source of "layer list is
inconsistent" errors and vispy segfaults.

`NapariBridge` is the single receiver. It is a `QObject` whose thread affinity is
the application's GUI thread -- enforced in `__init__`, so it does not matter which
thread constructs it -- carrying one internal signal. Qt's automatic connection
type does the rest: emitting from a worker queues the call onto the GUI thread,
emitting from the GUI thread runs it inline.

Two calling styles:

* **Fire-and-forget** (`wait=False`, the default for the convenience methods that
  do not produce anything): the worker returns immediately.
* **Blocking** (`submit(..., wait=True)`): the worker waits for the GUI thread to
  finish and gets the result or the exception back. This exists for callers that
  genuinely need the layer object -- `executor.py` passes the freshly created
  layer into the node's visualisation function. It always carries a timeout, so a
  wedged GUI thread cannot hang an acquisition forever.

The one rule this module cannot enforce for you: never call a blocking
`submit` from the GUI thread *onto* work that is waiting on the GUI thread. A
blocking submit made from the GUI thread simply runs inline, so the common case
is safe by construction.
"""
from __future__ import annotations

import logging
import threading

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger(__name__)

#: How long a worker will wait for the GUI thread before giving up (seconds).
DEFAULT_CALL_TIMEOUT_S = 10.0


class _Call:
    """One unit of work handed to the GUI thread, plus somewhere to put the result."""

    __slots__ = ('fn', 'args', 'kwargs', 'done', 'result', 'error')

    def __init__(self, fn, args, kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.done = threading.Event()
        self.result = None
        self.error = None


class NapariBridge(QObject):
    """Marshals napari mutations onto the GUI thread.

    Args:
        viewer: the napari viewer every operation is applied to. May be `None`
            at construction and set later via `set_viewer`, since the viewer
            outlives some of the objects that want to talk to it.
    """

    _call_requested = pyqtSignal(object)

    def __init__(self, viewer=None, parent=None):
        super().__init__(parent)
        self._viewer = viewer

        app = QApplication.instance()
        if app is not None and self.thread() is not app.thread():
            # Give the bridge GUI-thread affinity no matter who built it, so
            # `_call_requested` is always a *queued* connection from a worker.
            self.moveToThread(app.thread())

        self._call_requested.connect(self._run_call)

    # ------------------------------------------------------------------ viewer

    def set_viewer(self, viewer):
        self._viewer = viewer

    @property
    def viewer(self):
        return self._viewer

    # ------------------------------------------------------------- dispatching

    @staticmethod
    def on_gui_thread():
        """True when the caller is already the thread that owns the widgets."""
        app = QApplication.instance()
        if app is None:
            # No application: there is no separate GUI thread to marshal onto,
            # so run inline. This is the headless/test path.
            return True
        return QThread.currentThread() == app.thread()

    def submit(self, fn, *args, wait=False, timeout=DEFAULT_CALL_TIMEOUT_S, **kwargs):
        """Run `fn(viewer, *args, **kwargs)` on the GUI thread.

        Returns `fn`'s result when `wait` is true, otherwise `None`. A blocking
        call that times out raises `TimeoutError`; one whose `fn` raises
        re-raises that exception on the calling thread.
        """
        call = _Call(fn, args, kwargs)

        if self.on_gui_thread():
            self._run_call(call)
        else:
            self._call_requested.emit(call)
            if not wait:
                return None
            if not call.done.wait(timeout):
                raise TimeoutError(
                    'napari operation %r did not reach the GUI thread within %ss'
                    % (getattr(fn, '__name__', fn), timeout)
                )

        if call.error is not None:
            raise call.error
        return call.result

    def _run_call(self, call):
        try:
            call.result = call.fn(self._viewer, *call.args, **call.kwargs)
        except BaseException as exc:  # noqa: BLE001 -- handed back to the caller
            call.error = exc
            logger.exception('napari operation failed on the GUI thread')
        finally:
            call.done.set()

    # ------------------------------------------------------- layer operations

    def add_layer(self, kind, *, wait=True, timeout=DEFAULT_CALL_TIMEOUT_S, **kwargs):
        """Add a layer of `kind` ('image', 'points', 'shapes', ...) and return it.

        Blocking by default: every current caller uses the layer it just made.
        """
        def _add(viewer):
            return getattr(viewer, 'add_%s' % kind)(**kwargs)

        return self.submit(_add, wait=wait, timeout=timeout)

    def remove_layer(self, name, *, wait=False, timeout=DEFAULT_CALL_TIMEOUT_S):
        """Remove every layer called `name`. Silent when there is none."""
        def _remove(viewer):
            removed = 0
            for layer in list(viewer.layers):
                if layer.name == name:
                    viewer.layers.remove(layer)
                    removed += 1
            return removed

        return self.submit(_remove, wait=wait, timeout=timeout)

    def replace_layer(self, kind, *, name, wait=True,
                      timeout=DEFAULT_CALL_TIMEOUT_S, **kwargs):
        """Remove any layer called `name`, then add a fresh one -- atomically.

        Doing this as one GUI-thread call rather than a `remove_layer` followed
        by an `add_layer` matters: two separate hops leave a window in which the
        layer list has neither, and another thread's submit can land in it.
        """
        def _replace(viewer):
            for layer in list(viewer.layers):
                if layer.name == name:
                    viewer.layers.remove(layer)
            return getattr(viewer, 'add_%s' % kind)(name=name, **kwargs)

        return self.submit(_replace, wait=wait, timeout=timeout)

    def update_layer(self, name, attribute, value, *, wait=False,
                     timeout=DEFAULT_CALL_TIMEOUT_S):
        """Set one attribute on the named layer, if it exists."""
        def _update(viewer):
            for layer in viewer.layers:
                if layer.name == name:
                    setattr(layer, attribute, value)
                    return True
            return False

        return self.submit(_update, wait=wait, timeout=timeout)

    def move_to_top(self, name, selectLayer=True, *, wait=False,
                    timeout=DEFAULT_CALL_TIMEOUT_S):
        """Move the named layer to the top of the stack (no-op if absent)."""
        def _move(viewer):
            from glados_pycromanager.GUI.napariHelperFunctions import moveLayerToTop

            moveLayerToTop(viewer, name, selectLayer=selectLayer)

        return self.submit(_move, wait=wait, timeout=timeout)

    def set_dims_step(self, axes, values, *, wait=False,
                      timeout=DEFAULT_CALL_TIMEOUT_S):
        """Set several dimension steps in one call (see T-E1)."""
        def _set(viewer):
            viewer.dims.set_current_step(axes, values)

        return self.submit(_set, wait=wait, timeout=timeout)


def get_bridge(shared_data):
    """Return `shared_data`'s bridge, creating it on first use.

    Safe to call from any thread: `NapariBridge.__init__` gives the object
    GUI-thread affinity itself. Returns `None` when `shared_data` is `None`.
    """
    if shared_data is None:
        return None

    bridge = getattr(shared_data, '_napari_bridge', None)
    if bridge is None:
        bridge = NapariBridge(getattr(shared_data, 'napariViewer', None))
        shared_data._napari_bridge = bridge
    elif bridge.viewer is None:
        bridge.set_viewer(getattr(shared_data, 'napariViewer', None))
    return bridge
