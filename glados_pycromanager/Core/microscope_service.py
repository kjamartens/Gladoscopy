"""Single owner thread for all microscope access (T-B3).

Threading invariant 2 of `claude_throughput_project.md` says the core has
exactly one owning thread and every other thread submits requests to it.
T-B1 made concurrent access *safe* (`MicroscopeInterfaceLayer._hw_lock`); it did
not make it *fair*. On PYCROMANAGER_JAVA a bridge round trip was measured at
~257 ms, so a GUI-thread `get_position()` taking the lock steals that much
bandwidth from the frame path, in whatever order the OS happens to grant the
lock.

`MicroscopeService` owns one `MicroscopeInterfaceLayer` and runs every call to
it on its own thread, ordered by priority: `Priority.FRAME` for the live pull
loop, `Priority.NORMAL` for user intents, `Priority.LOW` for background
polling. Two ways in:

* `MicroscopeProxy` -- the same synchronous API as MIL, blocking *the caller's*
  thread on the reply. Worker and node code keeps its straight-line style.
* `submit(...)` / the `request_completed` signal -- fire-and-forget for GUI
  slots, which must never block on a reply (T-B4 migrates them).

**Streaming mode** is what keeps the frame path free of an extra hop: the live
sequence pull loop (T-C3) runs *as* the service loop rather than on a separate
worker, so the thread that owns the hardware is the thread that pulls the
frames. While streaming, the loop still drains a bounded number of queued
requests between two frame pulls, so a stage move issued during live mode is
serviced within a frame or two instead of waiting out the acquisition.

The service is deliberately not a `QThread` running `exec_()`: nothing here
needs a Qt event loop on the owner thread, and a plain daemon thread matches the
other worker threads in this codebase (`FrameRing`'s consumer, `ZarrFrameWriter`).
It is still a `QObject` so replies can reach GUI slots as queued signals.
"""
from __future__ import annotations

import functools
import itertools
import logging
import threading
import time
from enum import IntEnum
from queue import Empty, PriorityQueue

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

#: A blocking `call()` waits this long by default. Generous because a single
#: Java-bridge round trip is ~257 ms and a stage move can take seconds; it
#: exists to turn a wedged backend into an exception rather than a hang.
DEFAULT_CALL_TIMEOUT_S = 60.0

#: How long the idle loop blocks on the queue before re-checking the stop flag.
IDLE_POLL_S = 0.05

#: Queued requests serviced between two frame pulls while streaming. Bounded so
#: a burst of UI intents cannot starve the camera.
STREAM_REQUEST_BUDGET = 8


class Priority(IntEnum):
    """Lower value = serviced first."""

    FRAME = 0
    NORMAL = 10
    LOW = 20


class ServiceError(RuntimeError):
    """Base class for service-level failures (not backend failures)."""


class ServiceStopped(ServiceError):
    """The service was not running, or stopped with the request still queued."""


class ServiceTimeout(ServiceError, TimeoutError):
    """A blocking call did not get its reply in time."""


class Request:
    """One unit of work for the owner thread, plus its reply slot."""

    __slots__ = ("fn", "args", "kwargs", "priority", "label", "callback",
                 "result", "exception", "_done", "submitted_at", "started_at",
                 "finished_at")

    def __init__(self, fn, args=(), kwargs=None, priority=Priority.NORMAL,
                 label=None, callback=None):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs or {}
        self.priority = priority
        self.label = label or getattr(fn, "__name__", repr(fn))
        self.callback = callback
        self.result = None
        self.exception = None
        self._done = threading.Event()
        self.submitted_at = time.perf_counter()
        self.started_at = None
        self.finished_at = None

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def run(self) -> None:
        """Execute on the owner thread. Never raises into the loop."""
        self.started_at = time.perf_counter()
        try:
            self.result = self.fn(*self.args, **self.kwargs)
        except BaseException as exc:  # noqa: BLE001 - handed to the caller
            self.exception = exc
        finally:
            self.finished_at = time.perf_counter()
            self._done.set()
        self._fire_callback()

    def fail(self, exc: BaseException) -> None:
        """Complete the request without running it (service stopped)."""
        self.exception = exc
        self.finished_at = time.perf_counter()
        self._done.set()
        self._fire_callback()

    def _fire_callback(self) -> None:
        if self.callback is None:
            return
        try:
            self.callback(self)
        except Exception:  # pragma: no cover - defensive
            logger.exception("MicroscopeService callback for %r failed", self.label)

    def wait(self, timeout=DEFAULT_CALL_TIMEOUT_S):
        """Block until done and return the result, re-raising any exception."""
        if not self._done.wait(timeout):
            raise ServiceTimeout(
                f"MicroscopeService request {self.label!r} did not complete "
                f"within {timeout}s"
            )
        if self.exception is not None:
            raise self.exception
        return self.result


class MicroscopeService(QObject):
    """Owns a `MicroscopeInterfaceLayer` and executes every call on one thread."""

    #: Emitted with the completed `Request` after every request, successful or
    #: not, from the *owner* thread -- connect with the default AutoConnection
    #: so a GUI slot receives it on the GUI thread.
    request_completed = pyqtSignal(object)

    def __init__(self, mil, name: str = "MicroscopeService", parent=None):
        super().__init__(parent)
        self.mil = mil
        self.name = name
        self._queue: PriorityQueue = PriorityQueue()
        self._seq = itertools.count()
        self._thread = None
        self._stop = threading.Event()
        self._owner_ident = None
        self._streaming = None
        self._stream_idle_sleep = 0.0005
        self._stream_label = None
        self._lock = threading.Lock()
        # Methods already warned about being blocked on from the GUI thread, so
        # a per-frame slot cannot flood the log. Cleared on stop().
        self._gui_block_warned = set()

    # --- lifecycle -------------------------------------------------------

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop.is_set()

    def start(self) -> "MicroscopeService":
        if self.running:
            return self
        self._stop.clear()
        started = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, args=(started,), name=self.name, daemon=True
        )
        self._thread.start()
        started.wait(5.0)
        logger.info("%s started (owner thread ident=%s)", self.name, self._owner_ident)
        return self

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the owner thread and fail every still-queued request."""
        self.stop_streaming()
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
            if thread.is_alive():
                logger.warning("%s did not exit within %ss", self.name, timeout)
        self._thread = None
        self._owner_ident = None
        self._gui_block_warned.clear()
        self._drain_pending(ServiceStopped(f"{self.name} stopped"))

    def is_owner_thread(self) -> bool:
        return self._owner_ident is not None and threading.get_ident() == self._owner_ident

    # --- submission ------------------------------------------------------

    def submit(self, fn, *args, priority: Priority = Priority.NORMAL,
               callback=None, label=None, **kwargs) -> Request:
        """Queue `fn(*args, **kwargs)` for the owner thread and return its Request.

        Called *from* the owner thread the request runs inline -- MIL methods
        compose, and the streaming pull loop calls back in, so anything else
        would deadlock.
        """
        request = Request(fn, args, kwargs, priority, label=label, callback=callback)
        if self.is_owner_thread():
            self._execute(request)
            return request
        if not self.running:
            raise ServiceStopped(
                f"{self.name} is not running; cannot submit {request.label!r}"
            )
        self._queue.put((int(priority), next(self._seq), request))
        return request

    def call(self, fn, *args, priority: Priority = Priority.NORMAL,
             timeout: float = DEFAULT_CALL_TIMEOUT_S, label=None, **kwargs):
        """Submit and block *the calling thread* until the reply arrives."""
        request = self.submit(fn, *args, priority=priority, label=label, **kwargs)
        return request.wait(timeout)

    def call_mil(self, method_name: str, *args, **kwargs):
        """Convenience: run one MIL method by name on the owner thread."""
        return self.call(getattr(self.mil, method_name), *args,
                         label=f"MIL.{method_name}", **kwargs)

    def proxy(self, priority: Priority = Priority.NORMAL,
              timeout: float = DEFAULT_CALL_TIMEOUT_S) -> "MicroscopeProxy":
        """A MIL-shaped facade whose calls run on the owner thread."""
        return MicroscopeProxy(self, priority=priority, timeout=timeout)

    # --- streaming -------------------------------------------------------

    def start_streaming(self, pull_once, idle_sleep: float = 0.0005,
                        label: str = "stream") -> None:
        """Run `pull_once()` as the loop body until `stop_streaming()`.

        `pull_once` must return True when it produced a frame and False when the
        camera had nothing ready; on False the loop sleeps `idle_sleep` so an
        idle camera does not spin a core. Raising is treated as fatal for the
        stream: it is logged and streaming stops, leaving the service usable.
        """
        with self._lock:
            if self._streaming is not None:
                raise ServiceError(
                    f"{self.name} is already streaming ({self._stream_label!r})")
            self._streaming = pull_once
            self._stream_idle_sleep = idle_sleep
            self._stream_label = label
        logger.info("%s entering streaming mode (%s)", self.name, label)

    def stop_streaming(self) -> None:
        with self._lock:
            label = self._stream_label
            self._streaming = None
            self._stream_label = None
        if label is not None:
            logger.info("%s left streaming mode (%s)", self.name, label)

    @property
    def is_streaming(self) -> bool:
        return self._streaming is not None

    # --- the owner thread ------------------------------------------------

    def _loop(self, started: threading.Event) -> None:
        self._owner_ident = threading.get_ident()
        started.set()
        while not self._stop.is_set():
            pull = self._streaming
            if pull is None:
                try:
                    _, _, request = self._queue.get(timeout=IDLE_POLL_S)
                except Empty:
                    continue
                self._execute(request)
            else:
                self._drain(STREAM_REQUEST_BUDGET)
                try:
                    produced = pull()
                except Exception:
                    logger.exception(
                        "%s streaming callable raised; leaving streaming mode", self.name)
                    self.stop_streaming()
                    continue
                if not produced:
                    time.sleep(self._stream_idle_sleep)
        self._drain_pending(ServiceStopped(f"{self.name} stopped"))

    def _drain(self, budget: int) -> int:
        """Run up to `budget` queued requests without blocking."""
        done = 0
        while done < budget:
            try:
                _, _, request = self._queue.get_nowait()
            except Empty:
                break
            self._execute(request)
            done += 1
        return done

    def _execute(self, request: Request) -> None:
        request.run()
        if request.exception is not None:
            logger.debug("%s request %r raised %r", self.name, request.label,
                         request.exception)
        try:
            self.request_completed.emit(request)
        except RuntimeError:  # pragma: no cover - QObject already deleted
            pass

    def _drain_pending(self, exc: BaseException) -> None:
        while True:
            try:
                _, _, request = self._queue.get_nowait()
            except Empty:
                return
            request.fail(exc)

    # --- diagnostics -----------------------------------------------------

    def note_gui_block(self, label: str) -> None:
        """Warn once per method that a GUI-thread caller blocked on the service.

        Invariant 1 says the GUI thread must not block on hardware; until T-B4
        has migrated every slot, this makes the remaining ones visible instead
        of silent.
        """
        if label in self._gui_block_warned:
            return
        self._gui_block_warned.add(label)
        logger.warning(
            "%s: %s was called from the GUI thread and blocked on the reply "
            "(threading invariant 1). Submit the intent instead (T-B4).",
            self.name, label,
        )


def _on_gui_thread() -> bool:
    """True if the current thread is the Qt GUI thread (False without a QApplication)."""
    try:
        from PyQt5.QtCore import QCoreApplication, QThread
    except Exception:  # pragma: no cover - PyQt is a hard dependency
        return False
    app = QCoreApplication.instance()
    if app is None:
        return False
    return QThread.currentThread() == app.thread()


class MicroscopeProxy:
    """MIL's synchronous API, executed on the service's owner thread.

    Attribute access falls through to the real MIL for anything that is not
    callable (`core`, `mda`, the cache fields), so existing code that reads
    `MILcore.core` keeps working.
    """

    def __init__(self, service: MicroscopeService,
                 priority: Priority = Priority.NORMAL,
                 timeout: float = DEFAULT_CALL_TIMEOUT_S):
        object.__setattr__(self, "_service", service)
        object.__setattr__(self, "_priority", priority)
        object.__setattr__(self, "_timeout", timeout)
        object.__setattr__(self, "_wrappers", {})

    @property
    def service(self) -> MicroscopeService:
        return self._service

    @property
    def mil(self):
        return self._service.mil

    def with_priority(self, priority: Priority) -> "MicroscopeProxy":
        return MicroscopeProxy(self._service, priority=priority, timeout=self._timeout)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        attr = getattr(self._service.mil, name)
        if not callable(attr):
            return attr
        wrappers = self._wrappers
        wrapper = wrappers.get(name)
        if wrapper is None:
            wrapper = self._make_wrapper(name, attr)
            wrappers[name] = wrapper
        return wrapper

    def __setattr__(self, name, value):
        # Writes go to the real MIL -- a few call sites poke `mda` / `core`.
        setattr(self._service.mil, name, value)

    def _make_wrapper(self, name, attr):
        service = self._service
        priority = self._priority
        timeout = self._timeout
        label = f"MIL.{name}"

        @functools.wraps(attr)
        def _proxied(*args, **kwargs):
            if not service.running and not service.is_owner_thread():
                # No owner thread to submit to (never started, or already
                # stopped): fall back to the direct call, which T-B1's lock
                # still makes safe.
                return attr(*args, **kwargs)
            if not service.is_owner_thread() and _on_gui_thread():
                service.note_gui_block(label)
            return service.call(attr, *args, priority=priority,
                                timeout=timeout, label=label, **kwargs)

        return _proxied
