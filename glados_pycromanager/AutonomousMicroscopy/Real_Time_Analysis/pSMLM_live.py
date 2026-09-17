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

`pSMLM_image` accumulates in `visualise()` too, but without the guard, which is
why it is marked `"__replayable__": False` outright.
"""

import logging

import numpy as np

from glados_pycromanager.autonomous.registry import register

from .pSMLM import getLocalizationList, getLocalPeaks_rawIm

#: Linear upsampling factor of the super-resolution render.
SR_UPSAMPLING = 10

#: Half-width, in SR pixels, of the Gaussian stamped per localization.
SR_KERNEL_RADIUS = 3


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
            "run_delay": 20,
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
        self._stamped_frames = set()
        # The points layer's style is applied once, not per frame -- see visualise().
        self._points_styled = False
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
            logging.info('pSMLM_live: super-resolution canvas is now %s',
                         self.sr_canvas.shape)
        if self._kernel is None or self._kernel_sigma != sigma:
            self._kernel = _gaussian_kernel(sigma, SR_KERNEL_RADIUS).astype(np.float32)
            self._kernel_sigma = sigma

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
            napariLayer['pSMLM: analysed frame'].data = image
            # Accumulate the SR render here rather than in run(); see the module
            # docstring. Each frame contributes at most once, so replaying a frame
            # re-draws the localizations without double-counting them.
            self._ensure_canvas(image, float(kwargs.get('srSigma', 1.0)))
            frame_id = self._frame_id(metadata)
            if len(self.SMLMlocs) and (frame_id is None or frame_id not in self._stamped_frames):
                self._stamp(self.SMLMlocs)
                if frame_id is not None:
                    self._stamped_frames.add(frame_id)

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
        # the data shrinks, and only when there is something to clear.
        try:
            if len(points.selected_data):
                points.selected_data = set()
        except (AttributeError, TypeError):
            pass
        # Assigned last: the style events above therefore fire while the data and
        # napari's slice indices still agree with each other.
        points.data = coords

        napariLayer['pSMLM: SR render'].data = self.sr_canvas
        return napariLayer

    def _style_points(self, points):
        """Apply the point style once per layer. See visualise() for why not per frame."""
        if self._points_styled:
            return
        for attribute, value in (
                ('symbol', 'disc'),
                ('size', 8),
                ('face_color', [0, 0, 0, 0]),
                # napari renamed edge_* to border_*; set whichever exists.
                ('border_color', 'red'), ('edge_color', 'red'),
                ('border_width', 0.05), ('edge_width', 0.05)):
            try:
                setattr(points, attribute, value)
            except (AttributeError, ValueError, KeyError):
                pass
        self._points_styled = True
