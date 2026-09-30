"""T-F3: the log widget must not re-read the whole log on every tick.

`LoggerWidget.update_log_content` runs on the **GUI thread** every ~500 ms. It
used to `setPlainText(log_file.read())` -- throwing away and rebuilding the whole
document layout, at a cost that grows with the length of the session rather than
with the amount of new text. Measured on the widget itself: 13 ms at a 0.3 MB
log, 145 ms at 7 MB, 486 ms at 22 MB, *every tick*. An acquisition logs steadily,
so a long run spent much of the GUI thread rebuilding a log view and napari's
frame updates queued behind it -- the "live view only updates every ~300 ms"
report.

These tests pin the tail-follow contract rather than the timing: only new bytes
are read, a tick with nothing new does no read at all, and truncation is
survived.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    # This module's imports reach QtWebEngineWidgets, which refuses to load
    # after a QCoreApplication exists unless this attribute is already set.
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def widget(qapp, tmp_path, monkeypatch):
    """A LoggerWidget pointed at a log file we control.

    Built with `__new__`: the real `__init__` walks the AppData folder for the
    newest log file, which is not what these tests are about.
    """
    from PyQt5.QtWidgets import QPlainTextEdit

    from glados_pycromanager.GUI.FlowChart_dockWidgets import LoggerWidget

    log = tmp_path / "glados_INFO.log"
    log.write_text("")

    w = LoggerWidget.__new__(LoggerWidget)
    QPlainTextEdit.__init__(w)
    w.setReadOnly(True)
    w.setMaximumBlockCount(LoggerWidget.MAX_LOG_BLOCKS)
    w._log_offset = 0
    w.app_specific_folder = str(tmp_path)
    w.most_recent_file = log.name
    return w, log


def _append(log, text):
    with open(log, "a") as fh:
        fh.write(text)


def test_new_lines_appear(widget):
    w, log = widget
    _append(log, "first\nsecond\n")

    w.update_log_content()

    assert "first" in w.toPlainText()
    assert "second" in w.toPlainText()


def test_only_the_new_bytes_are_read(widget, monkeypatch):
    """The whole point: cost tracks new text, not total log size."""
    w, log = widget
    _append(log, "old\n" * 100)
    w.update_log_content()
    offset_after_first = w._log_offset
    assert offset_after_first > 0

    _append(log, "new line\n")
    reads = []
    real_open = open

    def counting_open(path, *a, **k):
        handle = real_open(path, *a, **k)
        if str(path) == str(log):
            original_read = handle.read

            def read(*args):
                data = original_read(*args)
                reads.append(len(data))
                return data

            handle.read = read
        return handle

    monkeypatch.setattr("builtins.open", counting_open)
    w.update_log_content()

    assert reads, "expected exactly one read of the delta"
    assert sum(reads) < 50, f"read {sum(reads)} chars for one new line"
    assert "new line" in w.toPlainText()


def test_a_tick_with_no_new_data_does_not_open_the_file(widget, monkeypatch):
    """Most ticks have nothing to show; those must cost a single stat."""
    w, log = widget
    _append(log, "content\n")
    w.update_log_content()

    def explode(*a, **k):
        raise AssertionError("re-opened the log with nothing new to read")

    monkeypatch.setattr("builtins.open", explode)
    w.update_log_content()  # must not raise


def test_no_blank_line_grows_at_the_bottom(widget):
    """appendPlainText adds its own block; a trailing newline would compound."""
    w, log = widget
    for i in range(5):
        _append(log, f"line {i}\n")
        w.update_log_content()

    assert w.toPlainText().split("\n") == [f"line {i}" for i in range(5)]


def test_truncation_is_survived(widget):
    """A rotated or truncated file must not leave the view frozen for the run."""
    w, log = widget
    _append(log, "before rotation\n" * 20)
    w.update_log_content()
    assert "before rotation" in w.toPlainText()

    log.write_text("after rotation\n")  # truncate
    w.update_log_content()

    assert "after rotation" in w.toPlainText()
    assert "before rotation" not in w.toPlainText()


def test_the_document_is_bounded(widget):
    """The full log is on disk; an unbounded document is what made repaints
    scale with session length."""
    from glados_pycromanager.GUI.FlowChart_dockWidgets import LoggerWidget

    w, log = widget
    _append(log, "".join(f"line {i}\n" for i in range(LoggerWidget.MAX_LOG_BLOCKS + 500)))
    w.update_log_content()

    assert w.blockCount() <= LoggerWidget.MAX_LOG_BLOCKS
    # It is the *newest* lines that survive.
    assert f"line {LoggerWidget.MAX_LOG_BLOCKS + 499}" in w.toPlainText()


def test_a_missing_log_file_is_not_fatal(widget):
    w, log = widget
    os.remove(log)

    w.update_log_content()  # must not raise
