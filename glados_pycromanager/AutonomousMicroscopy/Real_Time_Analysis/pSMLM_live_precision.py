"""pSMLM live + SR, plus a live NeNA precision / FRC resolution readout and stop criterion.

Everything `pSMLM_live` shows (analysed frame, localizations, SR render beside them),
plus one extra layer: a text overlay in the top-left corner of the analysed frame with

- the NeNA localization precision (Endesfelder et al. 2014),
- the FRC resolution (Nieuwenhuizen et al. 2013; blink-merged, see below),
- the number of localizations against the number the stop criterion asks for, and
- STOP: True/False.

Stop criterion
--------------
    required = 2.71 / (M * 3 * pi) / NeNA_um^2 * w_um * h_um
    STOP     = localizations so far > required

with M the `MFactor` parameter and w x h the field of view in um, taken from the
frames themselves (camera ROI in pixels x the Micro-Manager pixel size). It is only
*reported*; nothing stops the acquisition yet.

How it stays out of the frame path
----------------------------------
The estimator is `IncrementalNeNAFRC` from
`AutonomousMicroscopy/exploration_nena_frc/nena_frc_live.py` (additive state, ~65 ms
per update on 885k localizations). `run()` only appends the frame's localizations
(converted to nm) to a pending buffer; every `updateEveryNFrames` analysed frames the
buffer is handed to a background thread in this node's subprocess, which updates the
estimator and publishes a small `precision_status` dict. The numba kernels release
the GIL (`nogil=True`), so localization keeps running at frame rate while an update
is computed. If an update is still running when the next one is due, the frames
simply keep accumulating and go into the following update.

The first update pays the one-off numba compile (up to a minute cold, ~1.5 s once
cached on disk) and FFTW planning for the canvas size (cached as wisdom) - on that
background thread, not in run().

Caveats
-------
- NeNA pairs localizations in *consecutive* camera frames. The frame number is taken
  from Micro-Manager's `ImageNumber` when the metadata carries it (it counts camera
  frames, so frames the live 'latest' pull policy skipped stay skipped), else from
  the `time` axis. Frames the RT pipeline drops because the node was busy are simply
  missing: they reduce the pair count, they do not create false pairs. The overlay
  shows which fraction of frames was analysed.
- The FRC canvas covers the whole camera ROI at `frcPixelNm` (capped at
  `MAX_FRC_PIXELS`^2); if the cap makes the pixel coarser than ~FRC/2, the FRC finds
  no crossing and reports 'finer than Nyquist'.
- The localization count (and so STOP) counts raw localizations, as the criterion
  was written; the FRC uses blink-merged ones.
- A frame number going backwards means a new acquisition: the estimator restarts.
"""

import logging
import math
import threading
import time

import numpy as np

from glados_pycromanager.autonomous.registry import register

from .pSMLM_live import pSMLM_live as _PSMLMLive

#: Name of the text-overlay layer (the other three are pSMLM_live's).
PRECISION_LAYER = 'pSMLM: NeNA / FRC'

#: Largest FRC canvas side. The canvas holds 1 + frcSplits float32 planes, so 4096^2
#: with 3 splits is 268 MB inside the node's subprocess.
MAX_FRC_PIXELS = 4096

#: Metadata keys holding the pixel size in um, in the order they are tried.
PIXEL_SIZE_KEYS = ('PixelSize_um', 'PixelSizeUm', 'pixel_size_um')

#: Repeats of the same raw frame number after which that frame source is abandoned.
STUCK_FRAMES_BEFORE_SWITCH = 2

#: Number of initial frames whose full metadata is logged (INFO) for diagnosis.
METADATA_DUMP_FRAMES = 3

#: How long end() waits for a running update before doing the final one itself.
END_JOIN_TIMEOUT_S = 30.0


def __function_metadata__():
    return {
        "pSMLM_live_precision": {
            "required_kwargs": [
                {"name": "ROIradius", "description": "Fitting ROI radius (px)",
                 "default": 3, "type": int},
            ],
            "optional_kwargs": [
                {"name": "stdmult",
                 "description": "Detection threshold, in standard deviations",
                 "default": 2, "type": int},
                {"name": "srSigma",
                 "description": "Gaussian width (SR px) stamped per localization",
                 "default": 1.0, "type": float},
                {"name": "MFactor",
                 "description": "M in the stop criterion 2.71/(M*3*pi)/NeNA^2*w*h",
                 "default": 4.0, "type": float},
                {"name": "updateEveryNFrames",
                 "description": "Analysed frames between NeNA/FRC updates",
                 "default": 1000, "type": int},
                {"name": "frcMergeNm",
                 "description": "FRC only: merge locs in consecutive frames closer than this (nm, 0 = off)",
                 "default": 10.0, "type": float},
                {"name": "frcSplits",
                 "description": "Random half-splits for the FRC (1 = fastest, no +-)",
                 "default": 3, "type": int},
                {"name": "frcPixelNm",
                 "description": "FRC render pixel (nm)",
                 "default": 10.0, "type": float},
                {"name": "pixelSizeNm",
                 "description": "Camera pixel size (nm); 0 = from Micro-Manager",
                 "default": 0.0, "type": float},
                {"name": "restartOnFrameReset",
                 "description": "Restart NeNA/FRC when the frame number goes back (off: keep accumulating)",
                 "default": False, "type": bool},
            ],
            "help_string": ("pSMLM live + SR render, with a live NeNA precision / FRC "
                            "resolution readout and an 'enough localizations' stop flag."),
            "display_name": "pSMLM live + NeNA/FRC",
            "run_delay": 5,
            "visualise_delay": 100,
            "visualisation_type": "points",
            "input": [],
            "output": [],
            "__runInSubprocess__": True,
            # SMLMlocs as for pSMLM_live; the two status dicts are a few hundred bytes.
            # The estimator itself (tens to hundreds of MB of canvases) stays in the child.
            "__snapshot_attrs__": ["SMLMlocs", "precision_status", "precision_progress"],
            # Replaying a frame shows the status as it stood at that frame.
            "__replayable__": True,
        }
    }


def required_localizations(nena_nm, m_factor, w_um, h_um):
    """Localizations needed before stopping: 2.71 / (M * 3 * pi) / NeNA_um^2 * w * h."""
    return (2.71 / (m_factor * 3 * math.pi)) / ((nena_nm / 1000.0) ** 2) * w_um * h_um


def _load_estimator_module():
    # Imported lazily: it pulls in numba/scipy, and the main-process visualisation
    # shadow of this node never needs it.
    from glados_pycromanager.AutonomousMicroscopy.exploration_nena_frc import nena_frc_live
    return nena_frc_live


@register("pSMLM_live_precision.pSMLM_live_precision")
class pSMLM_live_precision(_PSMLMLive):

    def __init__(self, core, **kwargs):
        super().__init__(core, **kwargs)
        # Published to the main process every frame (see __snapshot_attrs__).
        self.precision_status = {'state': 'waiting'}
        self.precision_progress = {'pending_frames': 0, 'every': 0}
        # Child-process state, never snapshotted.
        self._lock = threading.Lock()
        self._pending = []               # [(frame_numbers, x_nm, y_nm)] not yet handed on
        self._pending_frames = 0
        self._busy = False
        self._worker = None
        self._generation = 0             # bumped on a new acquisition; stale results are dropped
        self._est = None
        self._est_generation = -1
        self._frame_source = None        # 'ImageNumber' | 'time' | 'counter', fixed per acquisition
        self._counter = -1
        self._frame_offset = 0           # renumbering after a frame-number reset (live mode)
        self._renumber_logged = False
        self._rejected_sources = set()   # frame sources seen stuck at one value
        self._last_raw = None
        self._stuck_count = 0
        self._metadata_dumps = 0
        self._last_frame = None
        self._first_frame = None
        self._frames_analysed = 0
        self._geometry = None            # (pixel_nm, w_um, h_um)
        self._text_styled = False
        self._text_color = None
        self._text_shown = None

    # -- analysis ---------------------------------------------------------

    def _pixel_size_nm(self, metadata, kwargs):
        override = float(kwargs.get('pixelSizeNm', 0) or 0)
        if override > 0:
            return override
        for key in PIXEL_SIZE_KEYS:
            try:
                value = float((metadata or {}).get(key) or 0)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value * 1000.0
        # pSMLM_live falls back to 1.0 when core is None (always, in the child).
        return self.pxsizeum * 1000.0 if self.pxsizeum and self.pxsizeum != 1.0 else None

    def _frame_number(self, metadata):
        metadata = metadata or {}
        if self._frame_source is None:
            if 'ImageNumber' in metadata and 'ImageNumber' not in self._rejected_sources:
                self._frame_source = 'ImageNumber'
            elif 'time' in (metadata.get('Axes') or {}) and 'time' not in self._rejected_sources:
                self._frame_source = 'time'
            else:
                self._frame_source = 'counter'
        try:
            if self._frame_source == 'ImageNumber':
                return int(metadata['ImageNumber'])
            if self._frame_source == 'time':
                return int(metadata['Axes']['time'])
        except (KeyError, TypeError, ValueError):
            pass
        self._counter += 1
        return self._counter

    def _restart(self):
        """New acquisition: drop everything accumulated for the previous one."""
        with self._lock:
            self._generation += 1
            self._pending = []
            self._pending_frames = 0
        self._first_frame = None
        self._last_frame = None
        self._frames_analysed = 0
        self._counter = -1
        self._frame_offset = 0
        self.precision_status = {'state': 'waiting'}

    def run(self, image, metadata, shared_data, core, **kwargs):
        message = super().run(image, metadata, shared_data, core, **kwargs)

        pixel_nm = self._pixel_size_nm(metadata, kwargs)
        every = max(1, int(kwargs.get('updateEveryNFrames', 1000)))
        if pixel_nm is None:
            if self.precision_status.get('state') != 'no pixel size':
                logging.info('pSMLM_live_precision: no pixel size (pixelSizeNm=%s, metadata keys %s, '
                             'pxsizeum=%s) - NeNA/FRC disabled until one is known',
                             kwargs.get('pixelSizeNm'), sorted((metadata or {}).keys()), self.pxsizeum)
            self.precision_status = {'state': 'no pixel size'}
            return message
        h_px, w_px = np.asarray(image).shape[-2:]
        self._geometry = (pixel_nm, w_px * pixel_nm / 1000.0, h_px * pixel_nm / 1000.0)

        if self._metadata_dumps < METADATA_DUMP_FRAMES:
            # Everything the frame carries, to find a real camera frame counter in live mode.
            self._metadata_dumps += 1
            logging.info('pSMLM_live_precision: metadata dump %d/%d: %s', self._metadata_dumps,
                         METADATA_DUMP_FRAMES,
                         {k: (v if len(repr(v)) <= 80 else repr(v)[:80] + '...')
                          for k, v in sorted((metadata or {}).items(), key=lambda kv: str(kv[0]))})

        first_call = self._frame_source is None
        raw_frame = self._frame_number(metadata)
        if self._last_raw is not None and raw_frame == self._last_raw and self._frame_source != 'counter':
            # A source stuck at one value (e.g. a camera that always reports ImageNumber 0) would
            # make every frame a 'reset' and the renumbering below leaves a gap after each, so
            # NeNA finds no consecutive frames at all. Drop the source and take the next one.
            self._stuck_count += 1
            if self._stuck_count >= STUCK_FRAMES_BEFORE_SWITCH:
                old = self._frame_source
                self._rejected_sources.add(old)
                self._frame_source = None
                raw_frame = self._frame_number(metadata)
                logging.info('pSMLM_live_precision: frame source %r stuck at %r for %d frames; switching to '
                             '%r (raw %s). ImageNumber=%r, Axes=%r', old, self._last_raw,
                             self._stuck_count + 1, self._frame_source, raw_frame,
                             (metadata or {}).get('ImageNumber'), (metadata or {}).get('Axes'))
                self._stuck_count = 0
        else:
            self._stuck_count = 0
        self._last_raw = raw_frame
        if first_call:
            logging.info('pSMLM_live_precision: first frame - pixel %.2f nm, image %dx%d px, frame source %r '
                         '(first raw frame %s), ImageNumber=%r, Axes=%r, updateEveryNFrames=%d',
                         pixel_nm, w_px, h_px, self._frame_source, raw_frame,
                         (metadata or {}).get('ImageNumber'), (metadata or {}).get('Axes'), every)
        frame = raw_frame + self._frame_offset
        if self._last_frame is not None and frame <= self._last_frame:
            if kwargs.get('restartOnFrameReset', False):
                logging.info('pSMLM_live_precision: frame number went back (%s -> %s); '
                             'restarting NeNA/FRC', self._last_frame, frame)
                self._restart()
                frame = raw_frame
            else:
                # Live mode has no real frame number (and a live restart - e.g. an exposure
                # change - resets it), so keep accumulating: continue the numbering after
                # the last frame, one frame apart so no NeNA pair spans the discontinuity.
                self._frame_offset = self._last_frame + 2 - raw_frame
                frame = raw_frame + self._frame_offset
                if not self._renumber_logged:
                    logging.info('pSMLM_live_precision: frame numbers are not increasing (live mode?); '
                                 'renumbering and continuing to accumulate (source %r, raw %s, last %s)',
                                 self._frame_source, raw_frame, self._last_frame)
                    self._renumber_logged = True
        self._last_frame = frame
        if self._first_frame is None:
            self._first_frame = frame
        self._frames_analysed += 1

        locs = self.SMLMlocs
        with self._lock:
            if len(locs):
                self._pending.append((np.full(len(locs), frame, np.int64),
                                      locs[:, 0] * pixel_nm, locs[:, 1] * pixel_nm))
            self._pending_frames += 1
            due = self._pending_frames >= every and not self._busy
            self.precision_progress = {'pending_frames': self._pending_frames, 'every': every,
                                       'busy': self._busy}
        if due:
            self._dispatch(dict(kwargs))
        return message

    def _dispatch(self, kwargs, final=False):
        with self._lock:
            if self._busy:
                return
            batch, self._pending = self._pending, []
            self._pending_frames = 0
            self._busy = True
            generation = self._generation
        if batch:
            frames = np.unique(np.concatenate([b[0] for b in batch]))
            n_locs = sum(len(b[0]) for b in batch)
            # NeNA only pairs locs in frame f with locs in frame f+1: gaps here mean few pairs.
            n_consecutive = int(np.sum(np.diff(frames) == 1))
            logging.info('pSMLM_live_precision: dispatching update%s - %d locs in %d frames with locs '
                         '(frames %d..%d), %d of those have their next frame present (NeNA needs these)',
                         ' (final)' if final else '', n_locs, frames.size, frames[0], frames[-1],
                         n_consecutive)
        else:
            logging.info('pSMLM_live_precision: dispatching update%s with NO localizations in the batch',
                         ' (final)' if final else '')
        self._worker = threading.Thread(target=self._update, args=(batch, generation, kwargs, final),
                                        name='pSMLM_live_precision update', daemon=True)
        self._worker.start()

    def _estimator_for(self, generation, kwargs):
        if self._est is not None and self._est_generation == generation:
            return self._est
        live = _load_estimator_module()
        pixel_nm, w_um, h_um = self._geometry
        fov_nm = max(w_um, h_um) * 1000.0
        frc_px = max(float(kwargs.get('frcPixelNm', 10.0)), 0.1)
        n = int(math.ceil(fov_nm / frc_px))
        if n > MAX_FRC_PIXELS:
            logging.warning('pSMLM_live_precision: FRC canvas capped at %d px (%.1f nm/px instead of %.1f)',
                            MAX_FRC_PIXELS, fov_nm / MAX_FRC_PIXELS, frc_px)
            n = MAX_FRC_PIXELS
        from scipy.fft import next_fast_len
        n = next_fast_len(max(n, 64), real=True)
        n += n % 2
        est = live.IncrementalNeNAFRC(fov_nm=fov_nm, origin_nm=(0.0, 0.0), n_pixels=n,
                                      frc_splits=max(1, int(kwargs.get('frcSplits', 3))),
                                      frc_merge_nm=float(kwargs.get('frcMergeNm', 10.0)))
        t0 = time.perf_counter()
        est.warmup()
        logging.info('pSMLM_live_precision: NeNA/FRC estimator ready (%dx%d FRC canvas at %.1f nm/px, '
                     'warm-up %.0f ms)', n, n, fov_nm / n, (time.perf_counter() - t0) * 1e3)
        self._est, self._est_generation = est, generation
        return est

    def _update(self, batch, generation, kwargs, final):
        """Background thread: fold the batch into the estimator and publish a status."""
        try:
            est = self._estimator_for(generation, kwargs)
            if batch:
                est.add(np.concatenate([b[0] for b in batch]),
                        np.concatenate([b[1] for b in batch]),
                        np.concatenate([b[2] for b in batch]))
            if final:
                est.finalize()
            res = est.update()
            n_within = int(est.fine_counts.sum())
            logging.info('pSMLM_live_precision: update done - %d locs total, %d NeNA pairs (%d closer than '
                         'r_max=%.0f nm), NeNA %.3f +- %.3f nm, FRC %.2f nm (%d FRC locs), last frame %d, '
                         '%.0f ms', res.n_locs, res.n_nena_pairs, n_within, est.r_max, res.nena_nm,
                         res.nena_err_nm, res.frc_nm, res.n_frc_locs, res.last_frame,
                         res.timings_ms.get('total', float('nan')))
            if not np.isfinite(res.nena_nm):
                if res.n_nena_pairs < 50:
                    logging.info('pSMLM_live_precision: NeNA is n/a - only %d consecutive-frame pairs (<50 '
                                 'needed); are frames being skipped (live pull policy "latest", RT drops) '
                                 'so few frames have their successor?', res.n_nena_pairs)
                else:
                    logging.info('pSMLM_live_precision: NeNA is n/a - the histogram fit failed '
                                 '(%d pairs, %d within r_max); last histogram %s',
                                 res.n_nena_pairs, n_within,
                                 getattr(est, '_last_nena', (None, None))[1])
            if generation != self._generation:
                logging.info('pSMLM_live_precision: update result dropped (acquisition restarted meanwhile)')
                return                                       # a newer acquisition started meanwhile
            pixel_nm, w_um, h_um = self._geometry
            m_factor = float(kwargs.get('MFactor', 4.0))
            required = (required_localizations(res.nena_nm, m_factor, w_um, h_um)
                        if np.isfinite(res.nena_nm) and res.nena_nm > 0 else float('nan'))
            span = (self._last_frame - self._first_frame + 1) if self._first_frame is not None else 0
            self.precision_status = {
                'state': 'ok',
                'nena_nm': res.nena_nm, 'nena_err_nm': res.nena_err_nm,
                'frc_nm': res.frc_nm, 'frc_err_nm': res.frc_err_nm,
                'frc_merge_nm': est.frc_merge_nm, 'frc_pixel_nm': est.pixel,
                'n_locs': res.n_locs, 'n_frc_locs': res.n_frc_locs,
                'required': required, 'm_factor': m_factor,
                'stop': bool(np.isfinite(required) and res.n_locs > required),
                'last_frame': res.last_frame,
                'analysed_fraction': self._frames_analysed / span if span > 0 else float('nan'),
                'fov_um': (w_um, h_um),
                'update_ms': res.timings_ms.get('total', float('nan')),
            }
        except Exception as exc:                             # never kill the node over the readout
            logging.exception('pSMLM_live_precision: NeNA/FRC update failed')
            self.precision_status = {'state': 'error', 'error': f'{type(exc).__name__}: {exc}'}
        finally:
            with self._lock:
                self._busy = False

    def end(self, core, **kwargs):
        """Final update including the frames since the last one and still-open blink chains."""
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(END_JOIN_TIMEOUT_S)
            if worker.is_alive():
                logging.warning('pSMLM_live_precision: an update was still running after %.0f s at end(); '
                                'skipping the final update (%d frames not included)',
                                END_JOIN_TIMEOUT_S, self._pending_frames)
                return super().end(core, **kwargs)
        logging.info('pSMLM_live_precision: end() - geometry %s, %d pending batches, estimator %s, '
                     '%d frames analysed, status %s', self._geometry, len(self._pending),
                     'present' if self._est is not None else 'none', self._frames_analysed,
                     self.precision_status.get('state'))
        if self._geometry is not None and (self._pending or self._est is not None):
            self._dispatch(dict(kwargs), final=True)
            if self._worker is not None:
                self._worker.join(END_JOIN_TIMEOUT_S)
            s = self.precision_status
            if s.get('state') == 'ok':
                logging.info('pSMLM_live_precision final: NeNA %.2f +- %.2f nm, FRC %.2f +- %.2f nm, '
                             '%d locs (%d needed at M=%g), STOP=%s', s['nena_nm'], s['nena_err_nm'],
                             s['frc_nm'], s['frc_err_nm'], s['n_locs'], s['required'], s['m_factor'],
                             s['stop'])
        return super().end(core, **kwargs)

    # -- visualisation ----------------------------------------------------

    def visualise_init(self):
        specs = list(super().visualise_init())
        specs.append({'name': PRECISION_LAYER, 'type': 'points', 'placement': 'overlay',
                      'scale': [self.pxsizeum, self.pxsizeum]})
        return specs

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        napariLayer = super().visualise(image, metadata, core, napariLayer, **kwargs)
        try:
            self._show_text(napariLayer[PRECISION_LAYER])
        except Exception:                                    # the readout must never break the overlay
            logging.debug('pSMLM_live_precision: text overlay update failed', exc_info=True)
        return napariLayer

    def _status_text(self):
        s = self.precision_status or {}
        p = self.precision_progress or {}
        state = s.get('state', 'waiting')
        progress = f"next update in {max(p.get('every', 0) - p.get('pending_frames', 0), 0)} frames"
        if p.get('busy'):
            progress = 'updating...'
        if state == 'waiting':
            if p.get('busy'):
                return ('NeNA / FRC: first update running\n'
                        '(the very first one compiles numba and plans the FFT - up to a minute, once)')
            return f"NeNA / FRC: collecting ({p.get('pending_frames', 0)}/{p.get('every', 0)} frames)"
        if state == 'no pixel size':
            return 'NeNA / FRC: pixel size unknown - set pixelSizeNm'
        if state == 'error':
            return f"NeNA / FRC error: {s.get('error', '?')}"

        def pm(v, e):
            if not np.isfinite(v):
                return 'n/a'
            return f'{v:.2f} +- {e:.2f} nm' if np.isfinite(e) else f'{v:.2f} nm'
        frc = pm(s['frc_nm'], s['frc_err_nm']) if np.isfinite(s['frc_nm']) else (
            f"finer than Nyquist ({2 * s['frc_pixel_nm']:.0f} nm)")
        merge = f" (merged <{s['frc_merge_nm']:g} nm)" if s.get('frc_merge_nm') else ''
        required = f"{s['required']:,.0f}" if np.isfinite(s['required']) else '?'
        return (f"NeNA  {pm(s['nena_nm'], s['nena_err_nm'])}\n"
                f"FRC   {frc}{merge}\n"
                f"locs  {s['n_locs']:,} / {required} needed (M = {s['m_factor']:g})\n"
                f"STOP: {s['stop']}\n"
                f"frame {s['last_frame']}, {100 * s['analysed_fraction']:.0f}% analysed, {progress}")

    def _show_text(self, layer):
        """One constant point at the frame's top-left corner carries the text. Its count
        never changes, so napari's async slicing cannot race it (see _push_points)."""
        if not self._text_styled:
            layer.data = np.zeros((1, 2))
            for name, value in (('size', 1), ('face_color', [0, 0, 0, 0]), ('border_color', [0, 0, 0, 0]),
                                ('edge_color', [0, 0, 0, 0]), ('border_width', 0), ('edge_width', 0)):
                try:
                    setattr(layer, name, value)
                except (AttributeError, ValueError, KeyError):
                    pass
            self._text_styled = True
        text = self._status_text()
        s = self.precision_status or {}
        color = 'lime' if s.get('stop') else ('red' if s.get('state') == 'error' else 'yellow')
        if color != self._text_color:
            layer.features = {'label': [text]}
            layer.text = {'string': '{label}', 'color': color, 'size': 10, 'anchor': 'upper_left'}
            self._text_color, self._text_shown = color, text
        elif text != self._text_shown:
            layer.features = {'label': [text]}
            layer.refresh_text()
            self._text_shown = text
