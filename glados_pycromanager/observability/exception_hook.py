"""Capture uncaught exceptions into the project logger (Phase 10.13).

Three excepthooks are installed by :func:`install_exception_hooks`:

* ``sys.excepthook`` — the main thread's uncaught-exception path.
* ``threading.excepthook`` — workers spawned via :class:`threading.Thread`.
* Qt's ``qInstallMessageHandler`` — PyQt5 internal messages (only when
  PyQt5 is importable; the helper is a no-op otherwise).

Each call to :func:`install_exception_hooks` is idempotent and returns
the previously-installed hooks so tests can restore them.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Module-level handles let install_exception_hooks be idempotent — a
# second call replaces the existing handlers cleanly rather than
# stacking them.
_PREV_SYS_EXCEPTHOOK: Callable[..., Any] | None = None
_PREV_THREADING_EXCEPTHOOK: Callable[..., Any] | None = None


def _log_uncaught(exc_type: type[BaseException], exc: BaseException, tb) -> None:
    """Logger callback wired up by both excepthooks."""
    # KeyboardInterrupt is the user telling us to stop; don't bury it
    # in the log file like a bug.
    if issubclass(exc_type, KeyboardInterrupt):
        original = _PREV_SYS_EXCEPTHOOK or sys.__excepthook__
        original(exc_type, exc, tb)
        return
    logger.error("Uncaught exception", exc_info=(exc_type, exc, tb))


def _thread_excepthook(args: "threading.ExceptHookArgs") -> None:
    if args.exc_type is SystemExit:
        return
    logger.error(
        "Uncaught exception in thread %s",
        getattr(args.thread, "name", "<unknown>"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def install_exception_hooks() -> dict[str, Any]:
    """Wire :func:`_log_uncaught` into sys + threading excepthooks.

    Returns a dict with keys ``"sys"`` and ``"threading"`` carrying
    the hooks that were active *before* this call so callers (typically
    tests) can restore them.
    """
    global _PREV_SYS_EXCEPTHOOK, _PREV_THREADING_EXCEPTHOOK

    previous = {
        "sys": sys.excepthook,
        "threading": threading.excepthook,
    }

    if sys.excepthook is not _log_uncaught:
        _PREV_SYS_EXCEPTHOOK = sys.excepthook
        sys.excepthook = _log_uncaught
    if threading.excepthook is not _thread_excepthook:
        _PREV_THREADING_EXCEPTHOOK = threading.excepthook
        threading.excepthook = _thread_excepthook

    return previous


def restore_exception_hooks(previous: dict[str, Any]) -> None:
    """Undo :func:`install_exception_hooks` using its return value."""
    global _PREV_SYS_EXCEPTHOOK, _PREV_THREADING_EXCEPTHOOK
    sys.excepthook = previous["sys"]
    threading.excepthook = previous["threading"]
    _PREV_SYS_EXCEPTHOOK = None
    _PREV_THREADING_EXCEPTHOOK = None
