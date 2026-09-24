import inspect
import logging
import os
import sys
import time
from collections import deque

import numpy as np
from scipy.ndimage import maximum_filter

# Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
from glados_pycromanager.autonomous.registry import register


def __function_metadata__():
    return {
        "PhaseCheckSIM": {
            "required_kwargs": [
            ],
            "optional_kwargs": [
                {"name": "PeakMode", "description": "Peak detection mode used once at calibration: 1d, 2d, 3d, or normal", "default": "normal", "type": str},
                {"name": "CalibrationFrames", "description": "Number of initial frames to average before detecting peaks once", "default": 8, "type": int},
                {"name": "TrackIndices", "description": "Comma-separated 1-indexed peak indices to track phase for, e.g. '1,3'", "default": "1", "type": str},
                {"name": "IntegrationRadius", "description": "Pixel radius of the disk integrated around each tracked peak", "default": 1, "type": int},
                {"name": "HistoryLength", "description": "Number of recent phase samples kept per tracked peak", "default": 200, "type": int},
                {"name": "ShowDebugOverlay", "description": "Show the calibration FFT with detected peaks circled instead of the phase-history plot", "default": False, "type": bool},
                {"name": "LogScale", "description": "Log-scale the FFT magnitude in the debug overlay", "default": True, "type": bool},
                {"name": "BGWindowDivisor", "description": "Divisor of max(shape) used to size the DC-suppression window", "default": 50, "type": int},
                {"name": "MinPeakDistDivisor", "description": "Divisor of max(shape) used to size the local-maxima search neighborhood", "default": 60, "type": int},
                {"name": "PeakThresholdNormal", "description": "Fraction of max FFT magnitude used as the peak threshold in 'normal'/axis-search steps", "default": 0.25, "type": float},
                {"name": "PeakThresholdRelaxed", "description": "Fraction of max FFT magnitude used as the relaxed peak threshold in 1d/2d/3d candidate search", "default": 0.05, "type": float},
                {"name": "AxisAngleTolerance", "description": "Tangent-angle tolerance for axis-aligned peak classification in 2d/3d mode", "default": 0.4, "type": float},
                {"name": "ColinearityTolerance", "description": "Normalized distance tolerance for the 3d mode's colinear second-peak test", "default": 0.2, "type": float},
                {"name": "PhaseColormap", "description": "Napari colormap applied to the displayed image layer", "default": "turbo", "type": str},
            ],
            "help_string": "Calibrates SIM illumination-fringe FFT peak locations from the first N averaged frames, then tracks the phase of selected peaks every frame and shows either a phase-history plot or a debug FFT/peak overlay.",
            "display_name": "SIM Phase Check",
            "run_delay": 0,
            "visualise_delay": 200,
            "visualisation_type": "image",
            "input": [],
            "output": [],
            # run() only touches the frame + its own kwargs (no core/shared_data/nodzInfo),
            # and per-frame fft2 + local-maxima search is CPU-bound -- isolate it like
            # FFT_im.py/SharpnessValue.py so it can never block the UI.
            "__runInSubprocess__": True,
            # What visualise() reads that run() produces. `firstLayerInit` is set by
            # visualise_init() on the main-process shadow instance and must not be
            # mirrored from the child.
            "__snapshot_attrs__": ["calibration_done", "peak_coords", "calib_fft_display",
                                    "phase_history", "running_avg"],
        }
    }

#-------------------------------------------------------------------------------------------------------------------------------
# Helper functions
#-------------------------------------------------------------------------------------------------------------------------------


def _disk_footprint(radius):
    """Boolean disk footprint of the given radius, for scipy.ndimage.maximum_filter."""
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    return (yy ** 2 + xx ** 2) <= radius ** 2


def _disk_indices(row, col, radius, shape):
    """(rows, cols) index arrays of every pixel within `radius` of (row, col),
    clipped to `shape`. A peak near the FFT edge simply integrates a partial disk."""
    rows = []
    cols = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy * dy + dx * dx <= radius * radius:
                y, x = row + dy, col + dx
                if 0 <= y < shape[0] and 0 <= x < shape[1]:
                    rows.append(y)
                    cols.append(x)
    return np.array(rows, dtype=int), np.array(cols, dtype=int)


def _classify_by_axis(candidates, center, mags, axis_tol_rad):
    """Splits candidate (row, col) points into horizontal-axis-like and
    vertical-axis-like pools, based on angular distance (mod pi) from the
    0 deg / 90 deg axes through `center`. No rotated-axis calibration input
    exists in this codebase, so the axes are always taken as axis-aligned."""
    horiz, vert = [], []
    center_row, center_col = center
    for (row, col) in candidates:
        dy = row - center_row
        dx = col - center_col
        theta = np.arctan2(dy, dx)
        horiz_off = np.mod(theta - 0.0, np.pi)
        horiz_off = min(horiz_off, np.pi - horiz_off)
        vert_off = np.mod(theta - np.pi / 2, np.pi)
        vert_off = min(vert_off, np.pi - vert_off)
        if horiz_off <= axis_tol_rad:
            horiz.append((row, col))
        if vert_off <= axis_tol_rad:
            vert.append((row, col))
    return horiz, vert


def _find_peaks(fft_complex, mode, thresh_normal, thresh_relaxed,
                 bg_window_divisor, min_peak_dist_divisor, axis_tol, colinear_tol):
    """Port of SIM_controller.m's snap_and_get_fft_peaksV2: finds FFT fringe
    peaks in `fft_complex` (already fftshift'd). Returns a flat list of
    (row, col) pixel coordinates, one entry per detected peak."""
    fft_mag = np.abs(fft_complex)
    shape = fft_mag.shape
    center = np.unravel_index(np.argmax(fft_mag), shape)
    center_row, center_col = center

    bg_win = max(round(max(shape) / bg_window_divisor), 1)
    fft_mag_search = fft_mag.copy()
    r0, r1 = max(center_row - bg_win, 0), min(center_row + bg_win + 1, shape[0])
    c0, c1 = max(center_col - bg_win, 0), min(center_col + bg_win + 1, shape[1])
    fft_mag_search[r0:r1, c0:c1] = 0

    min_dist = max(round(max(shape) / min_peak_dist_divisor), 1)
    footprint = _disk_footprint(min_dist)
    local_max = fft_mag_search == maximum_filter(fft_mag_search, footprint=footprint)

    # Hermitian half-plane restriction: a real image's FFT has a conjugate-
    # symmetric twin for every peak, point-reflected through `center`. Keep
    # only one of each pair, deterministically.
    half_plane = np.zeros(shape, dtype=bool)
    half_plane[center_row + 1:, :] = True
    half_plane[center_row, center_col + 1:] = True
    candidate_mask = local_max & half_plane

    # Thresholds are relative to the post-DC-removal magnitude (matching
    # MATLAB, which recomputes fft_mag from FFT_half *after* zeroing the DC
    # window) -- fft_mag.max() would still be dominated by the DC peak itself.
    search_max = fft_mag_search.max()

    def candidates_above(threshold):
        rows, cols = np.nonzero(candidate_mask & (fft_mag_search > threshold * search_max))
        pts = list(zip(rows.tolist(), cols.tolist()))
        pts.sort(key=lambda p: fft_mag_search[p[0], p[1]], reverse=True)
        return pts

    axis_tol_rad = np.arctan(axis_tol)

    if mode == "1d":
        cands = candidates_above(thresh_relaxed)
        return [cands[0]] if cands else []

    if mode == "normal":
        return candidates_above(thresh_normal)

    if mode == "2d":
        cands = candidates_above(thresh_relaxed)
        horiz, vert = _classify_by_axis(cands, center, fft_mag_search, axis_tol_rad)
        assert horiz or vert, \
            "[PhaseCheckSIM] 2d mode: no peak found near either the horizontal or vertical axis."
        result = []
        if horiz:
            result.append(max(horiz, key=lambda p: fft_mag_search[p[0], p[1]]))
        if vert:
            result.append(max(vert, key=lambda p: fft_mag_search[p[0], p[1]]))
        return result

    if mode == "3d":
        cands = candidates_above(thresh_relaxed)
        horiz, vert = _classify_by_axis(cands, center, fft_mag_search, axis_tol_rad)
        result = []
        for axis_pool in (horiz, vert):
            if not axis_pool:
                continue
            nearest = min(axis_pool, key=lambda p: (p[0] - center_row) ** 2 + (p[1] - center_col) ** 2)
            result.append(nearest)
            nearest_vec = np.array([nearest[0] - center_row, nearest[1] - center_col], dtype=float)
            nearest_dist = np.linalg.norm(nearest_vec)
            if nearest_dist == 0:
                continue
            line_dir = nearest_vec / nearest_dist
            for p in axis_pool:
                if p == nearest:
                    continue
                vec = np.array([p[0] - center_row, p[1] - center_col], dtype=float)
                proj = float(np.dot(vec, line_dir))
                perp_dist = float(np.linalg.norm(vec - proj * line_dir))
                if proj > nearest_dist and (perp_dist / max(proj, 1e-6)) < colinear_tol:
                    result.append(p)
                    break
        return result

    raise ValueError(f"[PhaseCheckSIM] Unknown PeakMode '{mode}' (expected 1d/2d/3d/normal)")


def _render_phase_plot(phase_history, width=512, height=256):
    """Rasterizes each tracked index's phase history (values in [-pi, pi])
    as a polyline into a single grayscale image, one constant pixel value
    per index so a single colormap still gives visually distinct lines."""
    canvas = np.zeros((height, width), dtype=np.float32)
    if not phase_history:
        return canvas

    for level, idx in enumerate(sorted(phase_history.keys())):
        hist = phase_history[idx]
        if len(hist) < 2:
            continue
        values = np.array(hist, dtype=float)
        n = len(values)
        xs = np.linspace(0, width - 1, n)
        ys = (1.0 - (values + np.pi) / (2 * np.pi)) * (height - 1)
        pixel_value = 50 + level * 60
        for i in range(n - 1):
            x0, y0, x1, y1 = xs[i], ys[i], xs[i + 1], ys[i + 1]
            n_steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
            for t in np.linspace(0, 1, n_steps):
                x = int(round(x0 + t * (x1 - x0)))
                y = int(round(y0 + t * (y1 - y0)))
                if 0 <= y < height and 0 <= x < width:
                    canvas[y, x] = pixel_value
    return canvas


def _burn_peak_circles(display, peak_coords, radius=4, value=None):
    """Returns a copy of `display` with a filled circle burned in at every
    peak coordinate, since a single image-type layer can't carry separate
    point markers."""
    out = display.copy()
    v = value if value is not None else (float(out.max()) * 1.1 if out.size else 1.0)
    footprint = _disk_footprint(radius)
    for (row, col) in peak_coords:
        r0, r1 = max(row - radius, 0), min(row + radius + 1, out.shape[0])
        c0, c1 = max(col - radius, 0), min(col + radius + 1, out.shape[1])
        fp_r0, fp_c0 = r0 - (row - radius), c0 - (col - radius)
        fp = footprint[fp_r0:fp_r0 + (r1 - r0), fp_c0:fp_c0 + (c1 - c0)]
        region = out[r0:r1, c0:c1]
        region[fp] = v
    return out


#-------------------------------------------------------------------------------------------------------------------------------
# Callable functions
#-------------------------------------------------------------------------------------------------------------------------------

@register("phase_check_sim.PhaseCheckSIM")
class PhaseCheckSIM:
    def __init__(self, core, **kwargs):
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__  # type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(), class_name, kwargs)  # type:ignore

        self.peak_mode = str(kwargs.get('PeakMode', 'normal')).lower()
        self.calibration_frames = max(int(kwargs.get('CalibrationFrames', 8)), 1)
        self.track_indices = [int(s) for s in str(kwargs.get('TrackIndices', '1')).split(',') if s.strip()]
        self.integration_radius = max(int(kwargs.get('IntegrationRadius', 1)), 0)
        self.history_length = max(int(kwargs.get('HistoryLength', 200)), 1)
        self.show_debug_overlay = str(kwargs.get('ShowDebugOverlay', False)).lower() in ('true', '1')
        self.log_scale = str(kwargs.get('LogScale', True)).lower() in ('true', '1')
        self.bg_window_divisor = max(int(kwargs.get('BGWindowDivisor', 50)), 1)
        self.min_peak_dist_divisor = max(int(kwargs.get('MinPeakDistDivisor', 60)), 1)
        self.peak_threshold_normal = float(kwargs.get('PeakThresholdNormal', 0.25))
        self.peak_threshold_relaxed = float(kwargs.get('PeakThresholdRelaxed', 0.05))
        self.axis_angle_tolerance = float(kwargs.get('AxisAngleTolerance', 0.4))
        self.colinearity_tolerance = float(kwargs.get('ColinearityTolerance', 0.2))
        self.phase_colormap = str(kwargs.get('PhaseColormap', 'turbo'))

        self.running_avg = None
        self.frames_seen = 0
        self.calibration_done = False
        self.peak_coords = None
        self.calib_fft_display = None
        self.phase_history = {}
        self._disk_index_cache = {}
        return None

    def _get_disk_indices(self, row, col, shape):
        key = (row, col, self.integration_radius)
        cached = self._disk_index_cache.get(key)
        if cached is None:
            cached = _disk_indices(row, col, self.integration_radius, shape)
            self._disk_index_cache[key] = cached
        return cached

    def run(self, image, metadata, shared_data, core, **kwargs):
        run_start = time.time()
        try:
            if not self.calibration_done:
                frame = image.astype(np.float64)
                if self.running_avg is None:
                    self.running_avg = frame.copy()
                    self.frames_seen = 1
                else:
                    self.frames_seen += 1
                    self.running_avg += (frame - self.running_avg) / self.frames_seen

                if self.frames_seen >= self.calibration_frames:
                    fft_complex = np.fft.fftshift(np.fft.fft2(self.running_avg))
                    self.peak_coords = _find_peaks(
                        fft_complex, self.peak_mode,
                        self.peak_threshold_normal, self.peak_threshold_relaxed,
                        self.bg_window_divisor, self.min_peak_dist_divisor,
                        self.axis_angle_tolerance, self.colinearity_tolerance)
                    mag = np.abs(fft_complex)
                    self.calib_fft_display = np.log1p(mag) if self.log_scale else mag
                    self.calibration_done = True
                    logging.info(f"PhaseCheckSIM calibration complete: {len(self.peak_coords)} peak(s) found "
                                 f"(mode='{self.peak_mode}')")
            else:
                fft_complex = np.fft.fftshift(np.fft.fft2(image.astype(np.float64)))
                for idx in self.track_indices:
                    if self.peak_coords is None or idx < 1 or idx > len(self.peak_coords):
                        logging.warning(f"PhaseCheckSIM: TrackIndices entry {idx} out of range "
                                         f"(only {0 if self.peak_coords is None else len(self.peak_coords)} "
                                         f"peak(s) calibrated) -- skipping")
                        continue
                    row, col = self.peak_coords[idx - 1]
                    rows, cols = self._get_disk_indices(row, col, fft_complex.shape)
                    if rows.size == 0:
                        continue
                    complex_sum = np.sum(fft_complex[rows, cols])
                    phase = float(np.angle(complex_sum))
                    hist = self.phase_history.setdefault(idx, deque(maxlen=self.history_length))
                    hist.append(phase)
        except Exception as e:
            logging.error(f"PhaseCheckSIM processing failed: {e}")

        logging.debug(f"PhaseCheckSIM processing time: {time.time() - run_start:.4f}s")

    def end(self, core, **kwargs):
        logging.info('ENDING PHASE CHECK SIM ANALYSIS')
        return

    def visualise_init(self):
        logging.info('INITIALISING VISUALISATION FOR PHASE CHECK SIM')
        layerName = 'SIM Phase Check'
        layerType = 'image'
        self.firstLayerInit = True
        return layerName, layerType

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        vis_time = time.time()

        if not self.calibration_done:
            display = self.running_avg if self.running_avg is not None else np.zeros((512, 512))
        elif self.show_debug_overlay:
            display = _burn_peak_circles(self.calib_fft_display, self.peak_coords or [])
        else:
            display = _render_phase_plot(self.phase_history)

        napariLayer.data = display

        if self.firstLayerInit:
            napariLayer.colormap = self.phase_colormap
            napariLayer.contrast_limits = [float(np.min(display)), float(np.max(display) + 1e-9)]
            self.firstLayerInit = False

        logging.debug(f"Visualising PhaseCheckSIM: {time.time() - vis_time:.4f}s")
