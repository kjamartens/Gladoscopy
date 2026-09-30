"""T-F2: `NodeItem.paint()` must not do disk I/O or mutate the model.

`paint()` used to construct a `QPixmap` **from disk** on every repaint -- so
dragging a node re-decoded a PNG per mouse-move event, per visible node -- build
two `QFontMetrics` objects and measure the same string twice per call, and
reassign `self.attrs` (model mutation from inside a render pass).

These tests pin the extracted, cached helpers and the fact that the render path
no longer reaches for a pixmap file or reorders attributes.
"""
from __future__ import annotations

import inspect
import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    # nodz_main reaches QtWebEngineWidgets via GUI.utils, which refuses to load
    # after a QCoreApplication exists unless this attribute is already set.
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def nodz(qapp):
    import glados_pycromanager.GUI.nodz.nodz_main as nodz_main

    return nodz_main


@pytest.fixture(autouse=True)
def _clear_caches(nodz):
    nodz._NODE_STATUS_PIXMAP_CACHE.clear()
    nodz._FONT_METRICS_CACHE.clear()
    nodz._TEXT_EXTENT_CACHE.clear()
    yield
    nodz._NODE_STATUS_PIXMAP_CACHE.clear()
    nodz._FONT_METRICS_CACHE.clear()
    nodz._TEXT_EXTENT_CACHE.clear()


# --------------------------------------------------------------- status icons


def _icon_folder(nodz):
    from glados_pycromanager.ui.widgets import builders

    folder = builders.findIconFolder()
    if not folder or not os.path.exists(os.path.join(folder, "node_pending.png")):
        pytest.skip("node status icons not available in this layout")
    return folder


def test_status_pixmap_is_read_from_disk_once(nodz, monkeypatch):
    folder = _icon_folder(nodz)

    reads = []
    real = nodz.QPixmap

    class CountingQPixmap(real):
        def __init__(self, *args, **kwargs):
            if args and isinstance(args[0], str):
                reads.append(args[0])
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(nodz, "QPixmap", CountingQPixmap)

    first = nodz._nodeStatusPixmap(folder, "idle")
    assert not first.isNull()
    assert len(reads) == 1

    for _ in range(50):
        assert nodz._nodeStatusPixmap(folder, "idle") is first
    assert len(reads) == 1, "a repaint must not re-decode the PNG"


def test_each_status_maps_to_its_own_icon(nodz):
    folder = _icon_folder(nodz)
    for status, filename in nodz._NODE_STATUS_ICON_FILES.items():
        nodz._nodeStatusPixmap(folder, status)
        assert (folder, filename) in nodz._NODE_STATUS_PIXMAP_CACHE


def test_unknown_status_falls_back_to_the_error_icon(nodz):
    """The original code's `else` branch painted the error icon."""
    folder = _icon_folder(nodz)
    unknown = nodz._nodeStatusPixmap(folder, "some-new-status")
    error = nodz._nodeStatusPixmap(folder, "error")
    assert unknown is error


def test_missing_icon_is_not_cached(nodz, tmp_path):
    pixmap = nodz._nodeStatusPixmap(str(tmp_path), "idle")
    assert pixmap.isNull()
    assert nodz._NODE_STATUS_PIXMAP_CACHE == {}


def test_no_pixmap_is_built_at_import_time(nodz):
    """Caches must fill lazily -- a QPixmap needs a live QApplication."""
    assert nodz._NODE_STATUS_PIXMAP_CACHE == {}


# --------------------------------------------------------------- font metrics


def test_font_metrics_are_cached_per_font(nodz, qapp):
    from PyQt5.QtGui import QFont

    a = nodz._fontMetrics(QFont("Arial", 12))
    assert nodz._fontMetrics(QFont("Arial", 12)) is a, "same font -> same metrics"

    b = nodz._fontMetrics(QFont("Arial", 9))
    assert b is not a, "a different point size is a different cache entry"


def test_text_extent_matches_qfontmetrics_and_is_cached(nodz, qapp):
    from PyQt5.QtGui import QFont, QFontMetrics

    font = QFont("Arial", 12)
    rect = QFontMetrics(font).boundingRect("SomeNodeName")
    assert nodz._textExtent(font, "SomeNodeName") == (rect.width(), rect.height())

    assert len(nodz._TEXT_EXTENT_CACHE) == 1
    for _ in range(10):
        nodz._textExtent(QFont("Arial", 12), "SomeNodeName")
    assert len(nodz._TEXT_EXTENT_CACHE) == 1


# ------------------------------------------------------------ attrs ordering


class _FakeNode:
    """Just enough of NodeItem to exercise the extracted ordering method."""

    _reorderAttrs = None  # replaced in the fixture below

    def __init__(self, spec):
        self.attrs = [name for name, _ in spec]
        self.attrsData = {
            name: {"topAttr": kind == "top", "bottomAttr": kind == "bottom"}
            for name, kind in spec
        }


@pytest.fixture
def make_node(nodz):
    def _make(spec):
        node = _FakeNode(spec)
        node._reorderAttrs = nodz.NodeItem._reorderAttrs.__get__(node)
        return node

    return _make


def test_reorder_puts_bottom_and_top_attrs_last(make_node):
    node = make_node(
        [("b1", "bottom"), ("s1", "plain"), ("t1", "top"), ("s2", "plain")]
    )
    node._reorderAttrs()
    assert node.attrs == ["s1", "s2", "b1", "t1"]


def test_reorder_is_idempotent_and_stable(make_node):
    node = make_node([("s1", "plain"), ("s2", "plain"), ("b1", "bottom")])
    node._reorderAttrs()
    first = list(node.attrs)
    node._reorderAttrs()
    assert node.attrs == first == ["s1", "s2", "b1"]


def test_reorder_does_not_reassign_when_already_ordered(make_node):
    node = make_node([("s1", "plain"), ("b1", "bottom")])
    node._reorderAttrs()
    before = node.attrs
    node._reorderAttrs()
    assert node.attrs is before, "an already-ordered list must not be replaced"


def test_reorder_tolerates_an_attr_without_data(make_node):
    node = make_node([("s1", "plain"), ("b1", "bottom")])
    node.attrs.append("orphan")
    node._reorderAttrs()
    assert set(node.attrs) == {"s1", "b1", "orphan"}


# ----------------------------------------------------- the render path itself


def test_paint_no_longer_touches_disk_or_reorders_attrs(nodz):
    source = inspect.getsource(nodz.NodeItem.paint)
    assert "QPixmap(" not in source, "paint() must use the cached status pixmap"
    assert "QFontMetrics(" not in source, "paint() must use cached font metrics"
    assert "self.attrs =" not in source, "paint() must not mutate the model"


def test_attribute_mutation_sites_reorder(nodz):
    for method in (nodz.NodeItem._createAttribute, nodz.NodeItem._deleteAttribute):
        assert "_reorderAttrs()" in inspect.getsource(method)
    assert "_reorderAttrs()" in inspect.getsource(nodz.Nodz.editAttribute)
