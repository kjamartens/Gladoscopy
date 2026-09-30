"""T-F1: the icon helpers must do their disk and pixel work once, not per call.

`findIconFolder()` ran an `importlib.util.find_spec` plus up to three
`os.path.exists` probes on *every* call, and `setWarningErrorInfoIcon()` did a
`QPixmap` disk read + PNG decode, a full-image numpy grayscale conversion, a
`QImage` rebuild and a smooth rescale on every call. Between them they were hit
3-4 times per warning update, which the 1 Hz nodz timer triggers roughly twice a
second for the whole session -- on the GUI thread.

These tests pin the caching contract (one lookup, one render per variant), not
the timings.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from glados_pycromanager.ui.widgets import builders  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _clear_caches():
    builders.findIconFolder.cache_clear()
    builders._ICON_PIXMAP_CACHE.clear()
    yield
    builders.findIconFolder.cache_clear()
    builders._ICON_PIXMAP_CACHE.clear()


def test_find_icon_folder_probes_the_filesystem_only_once(monkeypatch):
    """The path cannot change during a session, so neither should the lookup."""
    calls = []
    real_exists = os.path.exists
    monkeypatch.setattr(
        os.path, "exists", lambda p: (calls.append(p), real_exists(p))[1]
    )

    first = builders.findIconFolder()
    probes_after_first = len(calls)
    for _ in range(20):
        assert builders.findIconFolder() == first

    assert probes_after_first >= 0
    assert len(calls) == probes_after_first, "repeat calls must not re-probe disk"


def test_icon_folder_result_is_still_correct():
    folder = builders.findIconFolder()
    assert folder == "" or os.path.isdir(folder)


def test_pixmap_is_rendered_once_per_variant(qapp, monkeypatch):
    """A repeat call for the same variant must not re-decode or re-grayscale."""
    from PyQt5.QtWidgets import QLabel

    folder = builders.findIconFolder()
    if not folder or not os.path.exists(os.path.join(folder, "WarningIcon.png")):
        pytest.skip("icon assets not available in this layout")

    renders = []
    real_pixmap = builders.QPixmap

    class CountingQPixmap(real_pixmap):
        def __init__(self, *args, **kwargs):
            if args and isinstance(args[0], str):
                renders.append(args[0])
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(builders, "QPixmap", CountingQPixmap)

    label = QLabel()
    assert builders.setWarningErrorInfoIcon(label, "warning", folder) is label
    assert len(renders) == 1

    for _ in range(10):
        assert builders.setWarningErrorInfoIcon(label, "warning", folder) is label
    assert len(renders) == 1, "cached variant must not touch disk again"

    # A different variant is a different cache key and does render once more.
    assert builders.setWarningErrorInfoIcon(label, "warning", folder, alteration="none")
    assert len(renders) == 2
    assert builders.setWarningErrorInfoIcon(label, "error", folder)
    assert len(renders) == 3


def test_cached_pixmap_is_actually_applied_to_each_widget(qapp):
    """Sharing one QPixmap across widgets must still paint every widget."""
    from PyQt5.QtWidgets import QLabel

    folder = builders.findIconFolder()
    if not folder or not os.path.exists(os.path.join(folder, "WarningIcon.png")):
        pytest.skip("icon assets not available in this layout")

    first, second = QLabel(), QLabel()
    builders.setWarningErrorInfoIcon(first, "warning", folder)
    builders.setWarningErrorInfoIcon(second, "warning", folder)

    assert not first.pixmap().isNull()
    assert not second.pixmap().isNull()
    assert second.pixmap().size() == first.pixmap().size()


def test_no_pixmap_is_built_at_import_time():
    """The cache must stay empty until a caller asks -- QApplication may not exist."""
    assert builders._ICON_PIXMAP_CACHE == {}


def test_missing_icon_is_not_cached(qapp, tmp_path):
    """A null pixmap must stay retryable rather than being pinned forever."""
    from PyQt5.QtWidgets import QLabel

    label = QLabel()
    builders.setWarningErrorInfoIcon(label, "warning", str(tmp_path), alteration="none")
    assert builders._ICON_PIXMAP_CACHE == {}
