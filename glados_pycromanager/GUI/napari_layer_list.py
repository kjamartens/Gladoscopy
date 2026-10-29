"""Layer-list painting: keep thumbnails visible while a layer is re-sliced.

napari 0.7 marks a layer "not loaded" whenever an async slice request for it is
submitted, and its layer-list delegate then paints a loading spinner *instead
of* the thumbnail until a response with that same request id arrives. During an
acquisition the display moves `dims` for every displayed frame, and each move
re-slices every layer and cancels the still-pending request. A layer can stay
"not loaded" for the whole acquisition, so the layer list showed a spinner, not
a thumbnail, for MDA and Live alike.

`install_layer_list_patches()` replaces two methods of napari's private
`LayerDelegate` (pinned napari 0.7.0; `tests/test_napari_layer_list.py` checks
they still exist):

* the thumbnail is always painted, loaded or not, and
* the spinner is painted over it only once a layer has been unloaded *and* its
  thumbnail has not changed for `SPINNER_DELAY_S`, so a real long load still
  shows one. "Unloaded" alone is not enough: during an MDA a layer is unloaded
  for the whole acquisition while its slices (and thumbnail) keep arriving, so
  an unloaded-time rule alone left a permanent spinner over a working
  thumbnail. The thumbnail setter assigns a new array, so its identity is the
  progress signal.

The loading movie is still started while a layer is unloaded, as napari does:
its frame ticks are what repaint the list, which is how the delayed spinner
appears at all.
"""
from __future__ import annotations

import logging
import time
from weakref import WeakKeyDictionary

from qtpy.QtCore import Qt
from qtpy.QtGui import QPixmap

#: How long a layer must stay unloaded before the spinner is painted.
SPINNER_DELAY_S = 1.0

_load_state: WeakKeyDictionary = WeakKeyDictionary()
_installed = False


def _spinner_due(layer, loaded, now=None):
    """True once `layer` has been unloaded, with an unchanged thumbnail, for SPINNER_DELAY_S."""
    if layer is None:
        return not loaded
    if loaded:
        _load_state.pop(layer, None)
        return False
    if now is None:
        now = time.monotonic()
    thumb = getattr(layer, 'thumbnail', None)
    state = _load_state.get(layer)
    if state is None:
        state = _load_state[layer] = {'since': now, 'thumb': thumb, 'thumb_t': now}
    elif thumb is not state['thumb']:
        state['thumb'], state['thumb_t'] = thumb, now
    return (now - state['since'] >= SPINNER_DELAY_S
            and now - state['thumb_t'] >= SPINNER_DELAY_S)


def _paint_loading(self, painter, option, index):
    """Start the loading movie while unloaded; paint it only once loading has stalled."""
    from napari._qt.containers._base_item_model import ItemRole
    from napari._qt.containers.qt_layer_model import LoadedRole

    loaded = index.data(LoadedRole)
    if loaded:
        _spinner_due(index.data(ItemRole), True)
        return
    self._load_movie.start()
    if _spinner_due(index.data(ItemRole), False):
        load_rect = option.rect.translated(4, 8)
        h = index.data(Qt.ItemDataRole.SizeHintRole).height() - 16
        load_rect.setWidth(h)
        load_rect.setHeight(h)
        painter.drawPixmap(load_rect, self._load_movie.currentPixmap())


def _paint_thumbnail(self, painter, option, index):
    """Paint the thumbnail whether or not the layer is loaded."""
    from napari._qt.containers.qt_layer_model import LoadedRole, ThumbnailRole

    if index.data(LoadedRole):
        # As napari: the last layer to load pauses the movie all layers share.
        if index.model().sourceModel().all_loaded():
            self._load_movie.setPaused(True)
    thumb_rect = option.rect.translated(-2, 2)
    h = index.data(Qt.ItemDataRole.SizeHintRole).height() - 4
    thumb_rect.setWidth(h)
    thumb_rect.setHeight(h)
    image = index.data(ThumbnailRole)
    if image is not None:
        painter.drawPixmap(thumb_rect, QPixmap.fromImage(image))


def _paint(self, painter, option, index):
    """napari's paint, with the thumbnail drawn before the (delayed) spinner."""
    from qtpy.QtWidgets import QStyledItemDelegate

    option.textElideMode = Qt.TextElideMode.ElideMiddle
    self.get_layer_icon(option, index)
    QStyledItemDelegate.paint(self, painter, option, index)
    self._paint_thumbnail(painter, option, index)
    self._paint_loading(painter, option, index)


def install_layer_list_patches() -> bool:
    """Install the patched painting on napari's LayerDelegate. Idempotent."""
    global _installed
    if _installed:
        return True
    try:
        from napari._qt.containers._layer_delegate import LayerDelegate
    except ImportError:
        logging.warning('napari LayerDelegate not found; layer-list thumbnails unpatched')
        return False
    for name in ('paint', '_paint_loading', '_paint_thumbnail', 'get_layer_icon'):
        if not hasattr(LayerDelegate, name):
            logging.warning('napari LayerDelegate has no %s; layer-list thumbnails unpatched', name)
            return False
    LayerDelegate.paint = _paint
    LayerDelegate._paint_loading = _paint_loading
    LayerDelegate._paint_thumbnail = _paint_thumbnail
    _installed = True
    return True
