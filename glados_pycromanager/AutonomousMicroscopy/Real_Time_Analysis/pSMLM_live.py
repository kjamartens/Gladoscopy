"""Phasor SMLM with a live overlay and a super-resolution panel beside it.

Demonstrates the three things the single-layer visualisation contract could not do,
and is meant as the reference for writing nodes that use them:

1. **Several layers from one node.** `visualise_init()` returns a list of layer
   specs instead of a `(name, type)` pair, and `visualise()` receives a group it
   addresses by name.

2. **The analysed frame, not the newest one.** The raw live layer always shows the
   frame that just arrived, while the localizations belong to the frame the
   analysis last finished -- so at 50 ms/frame the circles appear to sit one frame
   behind the image under them. This node draws the analysed frame into its own
   layer, so the localizations sit on the exact frame they came from. It needs no
   extra snapshot attribute: `visualise()` already receives that frame as its
   `image` argument, because both producers hand on the frame they fed to `run()`.

3. **A mixed layout.** napari's grid mode is global -- every layer tiled, or every
   layer stacked -- but here the analysed frame and its localizations want to be
   overlaid while the SR render sits beside them. A layer spec's `placement` says
   so and Glados computes the offset, so this file stays layout-free.

Where the SR canvas is accumulated is the one real design decision here, and it
is a trade-off rather than a clean win.

Accumulating it in `run()` would make it part of the per-frame snapshot, and so
fully replayable -- scrubbing to frame N would show the reconstruction exactly as
it stood at frame N. It is also unaffordable: the canvas is the frame upsampled
10x in each axis, so it is 100 MB at a 512x512 camera frame and 400 MB at
1024x1024, and the snapshot is built *per frame* and shipped across the subprocess
boundary. Snapshotting it would cost more per frame than the raw data.

So it is accumulated in `visualise()` instead, from the localization list -- which
is a few KB -- with a guard against stamping the same frame twice when a frame is
revisited. The consequence, stated plainly:

- the analysed-frame and localization layers replay exactly, frame by frame;
- the SR panel is cumulative and does **not** rewind when you scrub. It shows the
  full reconstruction built so far, which is generally what you want from it.

Accumulating it cheaply is only half the problem: *handing it to napari* is the
other half, and that is what made this node unable to keep up at ~30 fps. Being
cumulative, the panel carries no per-frame information, so it is refreshed on a
`SR_REFRESH_INTERVAL_S` timer rather than once per analysed frame, and refreshed
in place (napari already holds this exact array) rather than re-assigned. The
localization and analysed-frame layers still update every frame; only the SR
panel lags, by at most that interval.

`pSMLM_image` accumulates in `visualise()` too, but without the guard, which is
why it is marked `"__replayable__": False` outright.
"""

import collections
import logging
import time

import numpy as np

from glados_pycromanager.autonomous.registry import register

from .pSMLM import getLocalizationList, getLocalPeaks_rawIm

#: Linear upsampling factor of the super-resolution render.
SR_UPSAMPLING = 10

#: Half-width, in SR pixels, of the Gaussian stamped per localization.
SR_KERNEL_RADIUS = 3

#: Smallest points buffer. The buffer only ever grows (see _push_points), so this
#: is just the size below which growing is not worth the churn.
MIN_POINTS_CAPACITY = 64

#: Minimum wall-clock gap between two refreshes of the super-resolution panel.
#: The canvas is the frame upsampled 10x per axis -- 26 MB at a 256x256 camera,
#: 100 MB at 512, 400 MB at 1024 -- and handing it to napari re-slices it and
#: re-uploads it to the GPU. It is a *cumulative* reconstruction, so unlike the
#: localization overlay it carries no per-frame information and nothing is lost
#: by refreshing it on a timer instead of once per analysed frame. Before this,
#: `_sr_version` was bumped on every frame that had any localization at all, so
#: the version guard below effectively never held during an acquisition and the
#: full array went to napari ~10x/s on the GUI thread.
SR_REFRESH_INTERVAL_S = 0.5

#: Cap on the set of frame keys already stamped into the SR canvas. Unbounded,
#: this grew one tuple per analysed frame for the whole session. Evicting the
#: oldest keys only risks double-counting a frame that is both older than this
#: many frames *and* scrubbed back to, which is a far better trade than the leak.
MAX_STAMPED_FRAMES = 50_000


def __function_metadata__():
    return {
        "pSMLM_live": {
            "required_kwargs": [
                {"name": "ROIradius", "description": "Fitting ROI radius (px)",
                 "default": 3, "type": int}
            ],
            "optional_kwargs": [
                {"name": "stdmult",
                 "description": "Detection threshold, in standard deviations",
                 "default": 2, "type": int},
                {"name": "srSigma",
                 "description": "Gaussian width (SR px) stamped per localization",
                 "default": 1.0, "type": float},
            ],
            "help_string": ("Phasor SMLM showing the localizations on the frame they "
                            "were found in, with a super-resolution render beside it."),
            "display_name": "pSMLM live + SR",
            "run_delay": 5,
            "visualise_delay": 100,
            "visualisation_type": "points",
            "input": [],
            "output": [],
            "__runInSubprocess__": True,
            # Everything visualise() reads that run() writes -- deliberately just
            # the localization list. `sr_canvas` is NOT here: it is 100-400 MB
            # depending on frame size and would be snapshotted per frame. See the
            # module docstring for the trade-off that follows from that.
            "__snapshot_attrs__": ["SMLMlocs"],
            # The localizations replay exactly; the SR panel is cumulative.
            "__replayable__": True,
        }
    }


def _gaussian_kernel(sigma, radius):
    """A small normalised Gaussian, stamped once per localization."""
    grid = np.arange(-radius, radius + 1, dtype=float)
    yy, xx = np.meshgrid(grid, grid, indexing='ij')
    kernel = np.exp(-(yy ** 2 + xx ** 2) / (2.0 * max(sigma, 1e-6) ** 2))
    total = kernel.sum()
    return kernel / total if total else kernel


@register("pSMLM_live.pSMLM_live")
class pSMLM_live:

    def __init__(self, core, **kwargs):
        self.SMLMlocs = np.empty((0, 2))
        self.sr_canvas = np.zeros((1, 1), dtype=np.float32)
        self._frame_shape = None
        self._kernel = None
        self._kernel_sigma = None
        # Frames already stamped into the SR canvas, so that scrubbing back and
        # forth over an acquisition does not count the same localizations twice.
        # Bounded: the deque records insertion order so the oldest keys can be
        # evicted once MAX_STAMPED_FRAMES is reached.
        self._stamped_frames = set()
        self._stamped_order = collections.deque()
        # The points layer's style is applied once, not per frame -- see visualise().
        self._points_styled = False
        # Bumped whenever the SR canvas changes, so visualise() can skip re-pushing
        # an unchanged (and very large) array to napari.
        self._sr_version = 0
        self._sr_pushed_version = -1
        # Wall clock of the last SR refresh, for the SR_REFRESH_INTERVAL_S gate.
        self._sr_last_push = 0.0
        # The points layer's array is a fixed-capacity buffer that only grows --
        # see _push_points for why its *length* must not follow the localization
        # count.
        self._points_capacity = 0
        # Pixel size is only used to scale the layers; a subprocess-isolated node
        # gets core=None, so fall back rather than failing to start.
        try:
            self.pxsizeum = core.get_pixel_size_um()
        except Exception:
            self.pxsizeum = 1.0
        if not self.pxsizeum:
            self.pxsizeum = 1.0

    # -- analysis ---------------------------------------------------------

    def _ensure_canvas(self, image, sigma):
        """(Re)allocate the SR canvas when the frame size or kernel changes."""
        if self._frame_shape != image.shape:
            self._frame_shape = image.shape
            self.sr_canvas = np.zeros(
                (image.shape[0] * SR_UPSAMPLING, image.shape[1] * SR_UPSAMPLING),
                dtype=np.float32)
            self._sr_version += 1
            logging.info('pSMLM_live: super-resolution canvas is now %s',
                         self.sr_canvas.shape)
        if self._kernel is None or self._kernel_sigma != sigma:
            self._kernel = _gaussian_kernel(sigma, SR_KERNEL_RADIUS).astype(np.float32)
            self._kernel_sigma = sigma

    def _note_stamped(self, frame_id):
        """Record that `frame_id` has contributed to the SR canvas, bounded."""
        self._stamped_frames.add(frame_id)
        self._stamped_order.append(frame_id)
        while len(self._stamped_order) > MAX_STAMPED_FRAMES:
            self._stamped_frames.discard(self._stamped_order.popleft())

    def _stamp(self, locs):
        """Add each localization to the SR canvas."""
        radius = SR_KERNEL_RADIUS
        height, width = self.sr_canvas.shape
        for x, y in locs:
            col = int(round(x * SR_UPSAMPLING))
            row = int(round(y * SR_UPSAMPLING))
            if not (radius <= row < height - radius and radius <= col < width - radius):
                continue
            self.sr_canvas[row - radius:row + radius + 1,
                           col - radius:col + radius + 1] += self._kernel

    def run(self, image, metadata, shared_data, core, **kwargs):
        peaks = getLocalPeaks_rawIm(image, int(kwargs['ROIradius']),
                                    stdmult=int(kwargs.get('stdmult', 2)))
        locs = getLocalizationList(peaks, image, int(kwargs['ROIradius']))
        # The only thing that crosses the process boundary, and the only thing
        # retained per frame for replay.
        self.SMLMlocs = np.asarray(locs, dtype=float).reshape(-1, 2)
        return f'pSMLM_live: {len(self.SMLMlocs)} localizations'

    def end(self, core, **kwargs):
        return None

    # -- visualisation ----------------------------------------------------

    def visualise_init(self):
        scale = [self.pxsizeum, self.pxsizeum]
        sr_scale = [self.pxsizeum / SR_UPSAMPLING, self.pxsizeum / SR_UPSAMPLING]
        return [
            # The frame the localizations below were actually found in.
            {'name': 'pSMLM: analysed frame', 'type': 'image',
             'colormap': 'gray', 'placement': 'overlay', 'scale': scale},
            {'name': 'pSMLM: localizations', 'type': 'points',
             'placement': 'overlay', 'scale': scale},
            # Beside the pair above, not on top of them.
            {'name': 'pSMLM: SR render', 'type': 'image',
             'colormap': 'magma', 'placement': 'right', 'scale': sr_scale},
        ]

    @staticmethod
    def _frame_id(metadata):
        """A hashable identity for the frame being visualised, or None."""
        axes = (metadata or {}).get('Axes')
        if not axes:
            return None
        return tuple(sorted((str(k), int(v)) for k, v in axes.items()))

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        # `image` is the frame this node's run() analysed, not the newest frame the
        # camera produced -- which is the whole point of showing it here.
        if image is not None:
            image = np.asarray(image)
            # Update in place where possible: assigning `.data` runs napari's
            # setter (_update_dims, the data event, a contrast rescan while
            # auto-contrast is on), where an in-place write plus refresh() does
            # not. Same idiom as the live display path in napariGlados.
            frame_layer = napariLayer['pSMLM: analysed frame']
            existing = getattr(frame_layer, 'data', None)
            if (existing is not None and getattr(existing, 'shape', None) == image.shape
                    and getattr(existing, 'dtype', None) == image.dtype):
                existing[:] = image
                frame_layer.refresh()
            else:
                frame_layer.data = image
            # Accumulate the SR render here rather than in run(); see the module
            # docstring. Each frame contributes at most once, so replaying a frame
            # re-draws the localizations without double-counting them.
            self._ensure_canvas(image, float(kwargs.get('srSigma', 1.0)))
            frame_id = self._frame_id(metadata)
            if len(self.SMLMlocs) and (frame_id is None or frame_id not in self._stamped_frames):
                self._stamp(self.SMLMlocs)
                self._sr_version += 1
                if frame_id is not None:
                    self._note_stamped(frame_id)

        points = napariLayer['pSMLM: localizations']
        # Style once, never per frame. Every one of these assignments emits a napari
        # event whose handler re-reads the layer's view data through the indices of
        # the *last completed* slice. napari 0.7 slices asynchronously, so doing that
        # on each frame -- right after the point count changed -- races a slice
        # response computed for the previous, longer point list, and the handler
        # indexes the new (shorter) array with the old indices:
        #     IndexError: index 52 is out of bounds for axis 0 with size 52
        # from Points._view_data / _update_slice_response. Setting the style once
        # removes the per-frame event storm that made the race easy to hit.
        self._style_points(points)

        # pSMLM reports (x, y); napari points are (row, col).
        coords = self.SMLMlocs[:, [1, 0]].copy() if len(self.SMLMlocs) else np.empty((0, 2))
        # A selection left over from the previous frame refers to points that may no
        # longer exist -- the same stale-index bug by another route. Cleared *before*
        # the data changes, and only when there is something to clear.
        try:
            if len(points.selected_data):
                points.selected_data = set()
        except (AttributeError, TypeError):
            pass
        # Assigned last: the style events above therefore fire while the data and
        # napari's slice indices still agree with each other.
        self._push_points(points, coords)

        # The SR canvas is up to 400 MB, and handing it to napari re-slices it,
        # rescans contrast and re-uploads it to the GPU. Two guards, because one
        # was not enough:
        #
        # * the version guard stops a *byte-identical* array being re-pushed --
        #   which is what every slider step did while scrubbing frames that were
        #   already stamped;
        # * the interval guard stops a genuinely-changed canvas being pushed at
        #   the overlay's rate. `_sr_version` is bumped on every frame that has
        #   any localization, so during an acquisition the version guard alone
        #   effectively never held and the full array went to napari ~10x/s on
        #   the GUI thread. The panel is cumulative, so refreshing it on a timer
        #   loses nothing.
        sr_layer = napariLayer['pSMLM: SR render']
        now = time.monotonic()
        if getattr(sr_layer, 'data', None) is not self.sr_canvas:
            # First push, or _ensure_canvas reallocated: napari is holding a
            # different (or no) array, so it must be given this one. Never
            # throttled -- the layer would otherwise show a stale canvas.
            sr_layer.data = self.sr_canvas
            self._sr_pushed_version = self._sr_version
            self._sr_last_push = now
        elif (self._sr_version != self._sr_pushed_version
                and now - self._sr_last_push >= SR_REFRESH_INTERVAL_S):
            # napari already holds this exact array and _stamp mutated it in
            # place, so refresh() re-renders it without going through the data
            # setter at all.
            sr_layer.refresh()
            self._sr_pushed_version = self._sr_version
            self._sr_last_push = now
        return napariLayer

    #(style attribute, value) pairs. The `current_*` form is what governs points
    #added *later*, which is the only form that works here -- see _style_points.
    #border_* is napari's newer name for edge_*; whichever exists is set.
    _POINT_STYLE = (
        ('symbol', 'disc'),
        ('size', 8),
        ('face_color', [0, 0, 0, 0]),
        ('border_color', 'red'), ('edge_color', 'red'),
        ('border_width', 0.05), ('edge_width', 0.05),
    )

    def _push_points(self, points, coords):
        """Show `coords` without changing the layer's array length.

        napari 0.7 slices asynchronously (and Glados runs it with NAPARI_ASYNC=1),
        so a slice response computed for one point list can arrive after a
        different one has been assigned. napari then indexes the *new* `shown`
        array with the *old* response's indices:

            self.__indices_view = value[self.layer.shown[value]]
            IndexError: index 21 is out of bounds for axis 0 with size 21

        Every reported instance of this is that shape -- index N into an array of
        size N -- i.e. purely a point-count change. So the count is kept out of it:
        the layer holds a fixed-capacity buffer and `shown` masks the unused rows,
        which means a stale index is always in range however late the response is.

        The buffer only ever grows. Shrinking it would reintroduce exactly the
        length change this exists to avoid, and the memory is trivial (two floats
        per slot). Surplus rows are parked on the first real localization rather
        than at the origin, so a response that briefly renders them unmasked shows
        nothing stray.
        """
        n = len(coords)
        if self._points_capacity < n or self._points_capacity == 0:
            #Geometric growth, so this is O(log n) length changes over a session
            #rather than one per frame.
            self._points_capacity = max(MIN_POINTS_CAPACITY, 2 * n)
        capacity = self._points_capacity

        buffer = np.zeros((capacity, 2), dtype=float)
        if n:
            buffer[:n] = coords
            buffer[n:] = coords[0]
        points.data = buffer
        try:
            points.shown = np.arange(capacity) < n
        except (AttributeError, ValueError):
            #Older/other napari without `shown`: fall back to the plain assignment,
            #which is correct but can still hit the race above.
            points.data = coords

    def _style_points(self, points):
        """Apply the point style once per layer. See visualise() for why not per frame.

        Uses `current_face_color` and friends rather than `face_color`. napari
        stores these **per point**, so assigning `face_color` to a layer that is
        still empty styles nothing and the points added on the next line come up
        with napari's defaults instead -- white filled discs with a grey border,
        rather than the open red rings this node wants. The `current_*` properties
        are the ones that govern points added later. The per-point arrays are set
        too, but only when the layer already holds points.
        """
        if self._points_styled:
            return
        has_points = False
        try:
            has_points = len(points.data) > 0
        except (AttributeError, TypeError):
            pass
        for attribute, value in self._POINT_STYLE:
            for name in (f'current_{attribute}', attribute if has_points else None):
                if name is None:
                    continue
                try:
                    setattr(points, name, value)
                except (AttributeError, ValueError, KeyError):
                    pass
        self._points_styled = True
