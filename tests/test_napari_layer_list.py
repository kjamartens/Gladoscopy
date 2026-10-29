"""Layer-list thumbnails stay visible while an acquisition re-slices layers.

napari 0.7 marks a layer "not loaded" for every async slice request, and its
layer-list delegate painted a spinner *instead of* the thumbnail until a
response for the latest request arrived. During an MDA every displayed frame
moves the dims, so the newest request was always pending and the MDA and Live
thumbnails were a permanent spinner. `napari_layer_list` always paints the
thumbnail and shows the spinner only after `SPINNER_DELAY_S`.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qtpy.QtCore import QRect, QSize, Qt
from qtpy.QtGui import QImage

from glados_pycromanager.GUI import napari_layer_list as nll


def test_napari_still_has_the_patched_delegate_methods():
    # Pinned napari 0.7.0: fail loudly if a napari upgrade moves these.
    from napari._qt.containers._base_item_model import ItemRole  # noqa: F401
    from napari._qt.containers._layer_delegate import LayerDelegate
    from napari._qt.containers.qt_layer_model import LoadedRole, ThumbnailRole  # noqa: F401

    for name in ('paint', '_paint_loading', '_paint_thumbnail', 'get_layer_icon'):
        assert hasattr(LayerDelegate, name)
    assert nll.install_layer_list_patches()
    assert nll.install_layer_list_patches()  # idempotent
    assert LayerDelegate._paint_thumbnail is nll._paint_thumbnail


class _Layer:
    pass


def test_spinner_only_after_the_delay():
    layer = _Layer()
    assert not nll._unloaded_long_enough(layer, False, now=100.0)
    assert not nll._unloaded_long_enough(layer, False, now=100.0 + nll.SPINNER_DELAY_S / 2)
    assert nll._unloaded_long_enough(layer, False, now=100.0 + nll.SPINNER_DELAY_S)


def test_loading_again_restarts_the_delay():
    layer = _Layer()
    nll._unloaded_long_enough(layer, False, now=0.0)
    nll._unloaded_long_enough(layer, True, now=5.0)
    assert not nll._unloaded_long_enough(layer, False, now=5.5)


def _index(loaded, layer=None):
    from napari._qt.containers._base_item_model import ItemRole
    from napari._qt.containers.qt_layer_model import LoadedRole, ThumbnailRole

    image = QImage(4, 4, QImage.Format.Format_RGBA8888)
    values = {
        LoadedRole: loaded,
        ThumbnailRole: image,
        ItemRole: layer,
        Qt.ItemDataRole.SizeHintRole: QSize(200, 32),
    }
    index = MagicMock()
    index.data.side_effect = lambda role: values.get(role)
    index.model.return_value.sourceModel.return_value.all_loaded.return_value = loaded
    return index


def _option():
    option = MagicMock()
    option.rect = QRect(0, 0, 200, 32)
    return option


@pytest.mark.parametrize('loaded', [True, False])
def test_thumbnail_is_painted_loaded_or_not(qapp, loaded):
    delegate = MagicMock()
    painter = MagicMock()
    nll._paint_thumbnail(delegate, painter, _option(), _index(loaded))
    painter.drawPixmap.assert_called_once()


def test_no_spinner_for_a_layer_that_just_started_loading(qapp):
    delegate = MagicMock()
    painter = MagicMock()
    nll._paint_loading(delegate, painter, _option(), _index(False, layer=_Layer()))
    delegate._load_movie.start.assert_called_once()  # keeps the list repainting
    painter.drawPixmap.assert_not_called()


def test_spinner_for_a_layer_loading_for_long(qapp, monkeypatch):
    layer = _Layer()
    nll._unloaded_long_enough(layer, False, now=0.0)
    monkeypatch.setattr(nll.time, 'monotonic', lambda: nll.SPINNER_DELAY_S + 1)
    delegate = MagicMock()
    painter = MagicMock()
    nll._paint_loading(delegate, painter, _option(), _index(False, layer=layer))
    painter.drawPixmap.assert_called_once()
