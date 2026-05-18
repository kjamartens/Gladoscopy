"""Phase 10.13 — uncaught exceptions land in the project logger."""

from __future__ import annotations

import logging
import sys
import threading

import pytest

from glados_pycromanager.observability import exception_hook


@pytest.fixture
def hook_active(caplog: pytest.LogCaptureFixture):
    """Install the hooks, raise level so the logger captures them, then restore."""
    caplog.set_level(logging.ERROR, logger=exception_hook.logger.name)
    previous = exception_hook.install_exception_hooks()
    try:
        yield previous
    finally:
        exception_hook.restore_exception_hooks(previous)


def test_sys_excepthook_logs_uncaught(
    hook_active, caplog: pytest.LogCaptureFixture
) -> None:
    try:
        raise RuntimeError("simulated main-thread crash")
    except RuntimeError:
        exc_type, exc, tb = sys.exc_info()
    sys.excepthook(exc_type, exc, tb)

    assert any(
        rec.levelno == logging.ERROR
        and "Uncaught exception" in rec.message
        and "simulated main-thread crash" in rec.exc_text
        for rec in caplog.records
    )


def test_thread_excepthook_logs_thread_name(
    hook_active, caplog: pytest.LogCaptureFixture
) -> None:
    seen: dict = {}

    def _boom() -> None:
        seen["ran"] = True
        raise ValueError("boom from worker")

    t = threading.Thread(target=_boom, name="GladosWorker-1")
    t.start()
    t.join()
    assert seen.get("ran") is True

    assert any(
        rec.levelno == logging.ERROR
        and "Uncaught exception in thread" in rec.message
        and "GladosWorker-1" in rec.message
        and "boom from worker" in (rec.exc_text or "")
        for rec in caplog.records
    )


def test_keyboard_interrupt_is_delegated_to_original_hook(
    hook_active,
) -> None:
    seen: dict = {}

    def fake_original(exc_type, exc, tb):
        seen["called"] = (exc_type, exc)

    # Pretend the *original* sys.excepthook is our spy.
    exception_hook._PREV_SYS_EXCEPTHOOK = fake_original

    try:
        raise KeyboardInterrupt("ctrl-c")
    except KeyboardInterrupt:
        exc_type, exc, tb = sys.exc_info()

    sys.excepthook(exc_type, exc, tb)
    assert seen.get("called")[0] is KeyboardInterrupt


def test_install_is_idempotent(hook_active) -> None:
    """Calling install twice does not stack handlers."""
    sys_hook_first = sys.excepthook
    thread_hook_first = threading.excepthook
    exception_hook.install_exception_hooks()
    assert sys.excepthook is sys_hook_first
    assert threading.excepthook is thread_hook_first


def test_restore_brings_back_original() -> None:
    pre_sys = sys.excepthook
    pre_thread = threading.excepthook
    previous = exception_hook.install_exception_hooks()
    try:
        assert sys.excepthook is exception_hook._log_uncaught
        assert threading.excepthook is exception_hook._thread_excepthook
    finally:
        exception_hook.restore_exception_hooks(previous)
    assert sys.excepthook is pre_sys
    assert threading.excepthook is pre_thread
