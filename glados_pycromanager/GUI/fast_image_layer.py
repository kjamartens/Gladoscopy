"""A napari `Image` layer that skips the async slicer for same-shape 2-D updates.

Every live/RT frame used to go through napari's full update path: `layer.data =`
(or an in-place write plus `layer.refresh()`) triggers `events.data`, which makes
the viewer recompute and reassign `dims.range`, then an async slice request on
napari's thread pool, a round trip back to the GUI thread (`_on_slice_ready`), a
thumbnail rebuild and a highlight update. Measured on the pinned napari 0.7.0 at
256x256 that is ~23 ms of GUI-thread time per frame, ~27 ms at 2048x2048.

For a plain 2-D numpy layer whose shape and dtype do not change, none of that
can change anything but the pixels: the extent, the dims ranges and the slice
geometry are all identical. `FastImage` does what napari itself does with
`NAPARI_ASYNC` off -- `set_view_slice()` + `_refresh_sync()` on the calling (GUI)
thread -- and throttles the thumbnail and the continuous auto-contrast rescan.
That is ~2.7 ms at 256x256 and ~3.6 ms at 2048x2048.

Semantics are napari's: `layer.data = x` adopts `x` by reference
(`layer.data is x` holds afterwards) and the view is re-sliced from it, so a node
that keeps and later mutates its array behaves exactly as with a stock layer.
Anything outside the fast-path conditions -- a shape/dtype/ndim change, a
non-numpy array (zarr, dask), multiscale, RGB, 3-D display, a hidden layer, or a
call off the GUI thread -- falls through to the stock `Image` behaviour.

It is a real `Image` subclass, so napari's vispy layer, layer controls, saving
and hover values all resolve by MRO as usual. Create it with `add_fast_image`.
"""
from __future__ import annotations

import time

import numpy as np
from napari.layers import Image

#: How often the layer-list thumbnail is rebuilt on the fast path. It is a
#: 64x64 preview; per-frame rebuilding was pure overhead.
THUMBNAIL_INTERVAL_S = 0.5

#: Default for `FastImage.contrast_every_n_frames` -- matches
#: `visualisation_config.contrast_refresh_every_n_frames`' default.
DEFAULT_CONTRAST_EVERY_N_FRAMES = 10


def _on_gui_thread() -> bool:
    try:
        from qtpy.QtCore import QCoreApplication, QThread
    except ImportError:  # pragma: no cover - napari always ships Qt here
        return False
    app = QCoreApplication.instance()
    # `==`, not `is`: PyQt may hand back distinct wrappers for the same QThread.
    return app is not None and QThread.currentThread() == app.thread()


class FastImage(Image):
    """napari `Image` with a synchronous, throttled update path for 2-D frames."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #: Continuous auto-contrast rescans every Nth fast update rather than
        #: every frame (napari's own async path rescans per slice).
        self.contrast_every_n_frames = DEFAULT_CONTRAST_EVERY_N_FRAMES
        self._fast_frames = 0
        self._fast_last_thumbnail = 0.0
        #: Diagnostics: how many updates took each path.
        self.fast_updates = 0
        self.slow_updates = 0

    # --- eligibility -------------------------------------------------------

    def _fast_path_ok(self, new=None) -> bool:
        current = self._data
        if new is not None and not (
            isinstance(new, np.ndarray)
            and isinstance(current, np.ndarray)
            and new.shape == current.shape
            and new.dtype == current.dtype
        ):
            return False
        return (
            isinstance(current, np.ndarray)
            and current.ndim == 2
            and not self.multiscale
            and not self.rgb
            and self.visible
            and self._slice_input.ndisplay == 2
            and not getattr(self, '_refresh_blocked', False)
            and _on_gui_thread()
        )

    # --- the fast update ---------------------------------------------------

    def _fast_update(self, *, highlight=True, extent=False, force=False) -> None:
        self._fast_frames += 1
        if (getattr(self, '_keep_auto_contrast', False)
                and self._fast_frames % max(int(self.contrast_every_n_frames), 1) == 0):
            self.reset_contrast_limits()
        now = time.monotonic()
        thumbnail = now - self._fast_last_thumbnail >= THUMBNAIL_INTERVAL_S
        if thumbnail:
            self._fast_last_thumbnail = now
        # Exactly napari's non-async refresh branch, minus a per-frame thumbnail.
        # Its slice handler rescans contrast on every slice while
        # `_keep_auto_contrast` is set, which would defeat the throttle above;
        # hold the flag off for the re-slice only.
        keep = getattr(self, '_keep_auto_contrast', False)
        self._keep_auto_contrast = False
        try:
            self.set_view_slice()
        finally:
            self._keep_auto_contrast = keep
        self._refresh_sync(thumbnail=thumbnail, data_displayed=True,
                           highlight=highlight, extent=extent, force=force)
        self.fast_updates += 1

    @property
    def data(self):
        return Image.data.fget(self)

    @data.setter
    def data(self, data) -> None:
        # `_fast_frames` doubles as "__init__ has finished": napari's own
        # constructor assigns data before our attributes exist.
        if hasattr(self, '_fast_frames') and self._fast_path_ok(data):
            # Image.data's setter minus `_update_dims` (shape/ndim unchanged)
            # and `events.data` (its listeners recompute dims ranges and ndim,
            # which cannot change here, and reassigning them re-slices).
            self._data_raw = data
            self._data = data
            self._fast_update()
            return
        if hasattr(self, 'slow_updates'):
            self.slow_updates += 1
        Image.data.fset(self, data)

    def refresh(self, event=None, *, thumbnail=True, data_displayed=True,
                highlight=True, extent=True, force=False) -> None:
        # Covers the in-place idiom `layer.data[:] = frame; layer.refresh()`.
        if data_displayed and hasattr(self, '_fast_frames') and self._fast_path_ok():
            self._fast_update(highlight=highlight, extent=extent, force=force)
            return
        if hasattr(self, 'slow_updates'):
            self.slow_updates += 1
        super().refresh(event, thumbnail=thumbnail, data_displayed=data_displayed,
                        highlight=highlight, extent=extent, force=force)


def add_fast_image(viewer, data, **kwargs) -> FastImage:
    """`viewer.add_image` for a single 2-D image, returning a `FastImage`.

    Keyword arguments are the `Image` constructor's. `channel_axis` (which makes
    `add_image` split one array into several layers) is not supported here --
    callers that need it should use `viewer.add_image`.
    """
    if 'channel_axis' in kwargs:
        raise TypeError('add_fast_image does not support channel_axis')
    if not hasattr(viewer, 'add_layer'):
        # A viewer stand-in (tests, a stub viewer) that only offers the
        # factory: a stock layer is always correct, just not accelerated.
        return viewer.add_image(data, **kwargs)
    layer = FastImage(data, **kwargs)
    viewer.add_layer(layer)
    return layer
