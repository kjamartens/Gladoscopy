"""Streaming NeNA precision + FRC resolution for a growing SMLM localization table.

`IncrementalNeNAFRC` takes localizations chunk by chunk (e.g. every 1000 frames)
and keeps only *additive* state, so an update costs about the same whether 10k or
10M localizations have been seen. Conventions follow webSMLM
(github.com/kjamartens/webSMLM), so the numbers are directly comparable:

NeNA  (Endesfelder et al. 2014)
    Nearest neighbour of every loc in frame f among the locs of frame f+1. The
    distances go into a fine (0.01 nm) histogram plus a count of pairs beyond r_max.
    A chunk adds only the pairs it completes; the newest frame is carried over as
    a tail, so pairs spanning a chunk border are neither lost nor double counted.
    An update rebuilds webSMLM's histogram from that state (range
    max(20, 4 x 25th percentile of all NN distances), 120 bins) and runs webSMLM's
    fit (Endesfelder model, unweighted Levenberg-Marquardt), warm-started from the
    previous update.

FRC   (Nieuwenhuizen et al. 2013)
    Every localization gets a random half-bit per split when it arrives and is
    scatter-added into persistent Hann-windowed canvases (2048^2, the window folded
    into the per-loc weight so the canvases never need re-windowing). Only the
    total image and half A of each split are stored: by FFT linearity
    F(B) = F(total) - F(A), so K splits cost K+1 FFTs instead of 2K. An update is
    one batched FFT + one fused ring-sum pass over all splits, independent of how
    many localizations exist. First 1/7 crossing from ring 3 on, +- = population SD
    over the splits (webSMLM uses 3). The curve is Gaussian-smoothed first
    (frc_smoothing='gauss', default); webSMLM's lighter 1-2-1 filter is available as
    'websmlm' for exact comparison - it lets noise trigger an early crossing, which
    reads ~1.5 nm coarser and ~6x noisier on the test file.

Backends are the winners of nena_frc_benchmark.py (see benchmark_results.md):
numba for the NN search, scatter-add and ring sums; pyfftw (plan + wisdom cached
on disk) or torch for the FFT. Each has a numpy/scipy fallback.

Measured on the 885k-loc test file, 20 updates of 1000 frames, warm caches:
~65 ms per update (3 splits), ~1.5 s one-off warm-up; webSMLM needs ~40 s once.

Usage:
    python nena_frc_live.py                          # stream the bundled CSV, 1000 frames per update
    python nena_frc_live.py --chunk-frames 500 --frc-splits 1

In code:
    est = IncrementalNeNAFRC(fov_nm=camera_fov_nm)
    est.warmup()                                     # JIT compile once (cached on disk afterwards)
    for chunk in stream:                             # frame-ordered chunks
        est.add(chunk['frame'], chunk['x'], chunk['y'])
        res = est.update()                           # -> NeNAFRCResult
"""
from __future__ import annotations

import argparse
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import fft as sfft
from scipy import optimize

HERE = Path(__file__).resolve().parent
N_THREADS = os.cpu_count() or 1
try:
    import psutil
    N_CORES = psutil.cpu_count(logical=False) or N_THREADS   # FFTW is slower on hyperthreads
except ImportError:  # pragma: no cover
    N_CORES = N_THREADS

try:
    from numba import njit, prange
    HAVE_NUMBA = True
except ImportError:  # pragma: no cover
    HAVE_NUMBA = False

_torch = None


def _get_torch():
    """torch is imported lazily: it is heavy and only the FFT uses it."""
    global _torch
    if _torch is None:
        try:
            import torch
            torch.set_num_threads(N_THREADS)
            _torch = torch
        except ImportError:  # pragma: no cover
            _torch = False
    return _torch or None


# ============================================================================ kernels
if HAVE_NUMBA:
    @njit(parallel=True, fastmath=True, cache=True, nogil=True)
    def _nn_next_frame(x, y, uniq, starts, r_max, out, nn):
        """out[i] = distance from loc i (frame f) to its nearest loc in frame f+1, inf if > r_max;
        nn[i] = that loc's index (-1 if none). At ~50 locs/frame brute force per frame pair
        beats any tree or grid (benchmark)."""
        r2max = r_max * r_max
        for k in prange(uniq.size - 1):
            if uniq[k + 1] != uniq[k] + 1:
                continue
            a1 = starts[k + 1]
            b1 = starts[k + 2]
            for i in range(starts[k], a1):
                best = r2max
                bj = -1
                xi = x[i]
                yi = y[i]
                for j in range(a1, b1):
                    dx = x[j] - xi
                    dy = y[j] - yi
                    d2 = dx * dx + dy * dy
                    if d2 < best:
                        best = d2
                        bj = j
                out[i] = math.sqrt(best) if bj >= 0 else np.inf
                nn[i] = bj

    @njit(cache=True, nogil=True)
    def _merge_chains(nn, d, r_merge, sx, sy, cnt, ended):
        """Merge blinking chains for the FRC. Forward pass over a frame-sorted table:
        loc i links to nn[i] (frame f+1) if d[i] < r_merge and i is the closest claimant
        of nn[i]; a link hands i's running (sum x, sum y, count) on to nn[i]. ended[i] is
        True for a loc that nobody continues, i.e. the last loc of its chain."""
        n = nn.size
        claim = np.full(n, -1, np.int64)       # closest i claiming each j
        for i in range(n):
            j = nn[i]
            if j >= 0 and d[i] < r_merge:
                c = claim[j]
                if c < 0 or d[i] < d[c]:
                    claim[j] = i
        for i in range(n):                     # links point forward (i < j): one pass suffices
            j = nn[i]
            if j >= 0 and claim[j] == i:
                sx[j] += sx[i]
                sy[j] += sy[i]
                cnt[j] += cnt[i]
                ended[i] = False

    @njit(parallel=True, cache=True, fastmath=True, nogil=True)
    def _scatter_add(x, y, halves, x0, y0, px, n, win, out):
        """Plane 0 of `out` is the total image, plane 1+s the first half of split s
        (the second half is total - first, never stored). Parallel over planes, so
        no two threads ever write the same pixel."""
        for p in prange(out.shape[0]):
            for i in range(x.size):
                if p > 0 and halves[p - 1, i] != 0:
                    continue
                ix = min(max(int((x[i] - x0) / px), 0), n - 1)
                iy = min(max(int((y[i] - y0) / px), 0), n - 1)
                out[p, iy, ix] += win[iy] * win[ix]

    @njit(parallel=True, fastmath=True, cache=True, nogil=True)
    def _ring_sums(F, ring, wcol, n_rings, n_chunks):
        """For every split s: ring sums of Re(A B*), |A|^2, |B|^2 with A = F[1+s],
        B = F[0] - F[1+s] (FFT linearity). One pass over the spectrum for all splits."""
        n_splits = F.shape[0] - 1
        ny, nx = ring.shape
        acc = np.zeros((n_chunks, n_splits, n_rings + 1, 3))
        rows = (ny + n_chunks - 1) // n_chunks
        for c in prange(n_chunks):
            for yy in range(c * rows, min(ny, (c + 1) * rows)):
                for xx in range(nx):
                    r = ring[yy, xx]
                    w = wcol[xx]
                    tr = F[0, yy, xx].real
                    ti = F[0, yy, xx].imag
                    for s in range(n_splits):
                        ar = F[1 + s, yy, xx].real
                        ai = F[1 + s, yy, xx].imag
                        br = tr - ar
                        bi = ti - ai
                        acc[c, s, r, 0] += w * (ar * br + ai * bi)
                        acc[c, s, r, 1] += w * (ar * ar + ai * ai)
                        acc[c, s, r, 2] += w * (br * br + bi * bi)
        tot = np.zeros((n_splits, n_rings + 1, 3))
        for c in range(n_chunks):
            tot += acc[c]
        return tot


def _frame_index(frame):
    uniq, starts = np.unique(frame, return_index=True)
    return uniq.astype(np.int64), np.append(starts, frame.size).astype(np.int64)


def nn_next_frame(x, y, frame, r_max, index=None):
    """(distance, index) of every loc's nearest neighbour in the next frame, for a
    frame-sorted table; (inf, -1) where there is none within r_max."""
    uniq, starts = _frame_index(frame) if index is None else index
    out = np.full(x.size, np.inf)
    nn = np.full(x.size, -1, np.int64)
    if HAVE_NUMBA:
        _nn_next_frame(x, y, uniq, starts, float(r_max), out, nn)
        return out, nn
    from scipy.spatial import cKDTree  # fallback: one tree, frame as a far-away 3rd axis
    L = 1e3 * (r_max + np.ptp(x) + np.ptp(y) + 1.0)
    tree = cKDTree(np.column_stack((x, y, frame * L)), balanced_tree=False, compact_nodes=False)
    out, nn = tree.query(np.column_stack((x, y, (frame + 1) * L)), k=1, distance_upper_bound=r_max, workers=-1)
    nn = np.where(np.isfinite(out), nn, -1).astype(np.int64)
    return out, nn


def merge_chains(nn, d, r_merge, sx, sy, cnt):
    """In-place chain merge (see _merge_chains); returns the `ended` mask."""
    ended = np.ones(nn.size, np.bool_)
    if HAVE_NUMBA:
        _merge_chains(nn, d, float(r_merge), sx, sy, cnt, ended)
        return ended
    cand = np.flatnonzero((nn >= 0) & (d < r_merge))
    cand = cand[np.lexsort((d[cand], nn[cand]))]              # per target j, closest claimant first
    keep = np.ones(cand.size, bool)
    keep[1:] = nn[cand[1:]] != nn[cand[:-1]]
    link = np.full(nn.size, -1, np.int64)
    link[cand[keep]] = nn[cand[keep]]
    for i in np.flatnonzero(link >= 0):                        # ascending = frame order
        j = link[i]
        sx[j] += sx[i]
        sy[j] += sy[i]
        cnt[j] += cnt[i]
        ended[i] = False
    return ended


# ============================================================================ NeNA fit (webSMLM's)
def _S(x, s):
    return x / (2 * s * s) * np.exp(-x * x / (4 * s * s))


def _nena_model(x, a1, s, a2, dc, w, a3):
    """Endesfelder: Rayleigh signal (precision s) + short-range Gaussian + linear background."""
    return a1 * _S(x, s) + a2 * np.exp(-(x - dc) ** 2 / (2 * w * w)) + a3 * x


def _nena_jac(x, a1, s, a2, dc, w, a3):
    S = _S(x, s)
    g = np.exp(-(x - dc) ** 2 / (2 * w * w))
    return np.column_stack((S, a1 * S * (x * x / (2 * s ** 3) - 2 / s), g,
                            a2 * g * (x - dc) / (w * w), a2 * g * (x - dc) ** 2 / w ** 3, x))


def _nena_p0(centers, y):
    """webSMLM's initial guess: signal peak -> s, largest bin in the upper half -> d_c."""
    n = centers.size
    i_pk = int(np.argmax(y))
    sig0 = max(3.0, centers[i_pk] / math.sqrt(2))
    j = n // 2 + int(np.argmax(y[n // 2:]))
    return np.array([y[i_pk] / max(1e-9, _S(sig0 * math.sqrt(2), sig0)), sig0, y[j] * 0.5, centers[j],
                     max(10.0, centers[j] * 0.5), 0.0])


def fit_nena(centers, y, p0=None):
    """Unweighted LM fit -> (s, SE(s), popt). SE = sqrt(residual variance x (J^T J)^-1)."""
    popt, pcov = optimize.curve_fit(_nena_model, centers, y, p0=_nena_p0(centers, y) if p0 is None else p0,
                                    jac=_nena_jac, method='lm', maxfev=4000)
    if not (popt[1] > 0) or not np.isfinite(pcov[1, 1]):
        raise RuntimeError('degenerate NeNA fit')
    return float(popt[1]), float(math.sqrt(max(pcov[1, 1], 0.0))), popt


# ============================================================================ helpers
class GrowableColumns:
    """Append-only columnar store with capacity doubling (amortised O(1) append)."""

    def __init__(self, dtypes: dict, capacity=1 << 16):
        self._cols = {k: np.empty((capacity,) + shape, dt) for k, (dt, shape) in dtypes.items()}
        self.size = 0

    def append(self, **cols):
        n = len(next(iter(cols.values())))
        need = self.size + n
        cap = len(next(iter(self._cols.values())))
        if need > cap:
            while cap < need:
                cap *= 2
            for k, a in self._cols.items():
                b = np.empty((cap,) + a.shape[1:], a.dtype)
                b[:self.size] = a[:self.size]
                self._cols[k] = b
        for k, v in cols.items():
            self._cols[k][self.size:need] = v
        self.size = need

    def __getitem__(self, k):
        return self._cols[k][:self.size]


@dataclass
class NeNAFRCResult:
    n_locs: int
    last_frame: int
    nena_nm: float
    nena_err_nm: float
    n_nena_pairs: int
    frc_nm: float
    frc_err_nm: float                                  # population SD over the splits (nan for 1 split)
    frc_per_split: list = field(default_factory=list)
    timings_ms: dict = field(default_factory=dict)
    n_frc_locs: int = 0                                # localizations in the FRC (after blink merging)


# ============================================================================ estimator
class IncrementalNeNAFRC:
    """Additive-state NeNA + FRC estimator. Feed frame-ordered chunks to add(), call update().

    fov_nm / origin_nm fix the FRC canvas (use the camera field of view in a live
    acquisition). Without fov_nm the canvas follows the data: it is sized from the
    first chunk and, when a later localization falls outside, grown x1.5 and
    re-rendered from the stored table (rare, amortised).

    frc_merge_nm (FRC only - NeNA always sees every localization): localizations in
    consecutive frames closer than this are one emitter staying on; each such chain is
    replaced by its mean position before it enters the FRC, so one blink cannot land in
    both halves and correlate with itself (the spurious correlation Nieuwenhuizen et al.
    2013 correct with their Q factor). The links reuse the NeNA nearest-neighbour search,
    so this is almost free. A chain still alive in the newest frame may continue in the
    next chunk, so it is held back until it ends - the FRC then lags by at most one
    frame's worth of chains. Call finalize() at the end of the acquisition to flush them.
    0 disables merging.
    """

    def __init__(self, r_max_nm=150.0, fov_nm=None, origin_nm=(0.0, 0.0), n_pixels=2048,
                 frc_splits=3, split='random', block_frames=10, seed=0,
                 nena_fine_bin_nm=0.01, nena_bins=120, threshold=1 / 7, fft_backend='auto',
                 frc_smoothing='gauss', frc_smooth_sigma=4e-4, frc_merge_nm=10.0):
        # frc_smoothing: 'gauss' (sigma frc_smooth_sigma in 1/nm), 'websmlm' (1-2-1) or 'none'
        self.frc_smoothing = frc_smoothing
        self.frc_smooth_sigma = float(frc_smooth_sigma)
        self.r_max = float(r_max_nm)
        self.frc_merge_nm = float(frc_merge_nm or 0.0)
        if self.frc_merge_nm > self.r_max:
            raise ValueError('frc_merge_nm must not exceed r_max_nm (the links reuse the NeNA search)')
        self._finalized = False
        self.n = int(n_pixels)
        self.n_splits = 1 if split != 'random' else int(frc_splits)
        self.split = split
        self.block_frames = int(block_frames)
        self.rng = np.random.default_rng(seed)
        self.threshold = threshold
        self.fft_backend = fft_backend
        self._fft_plans = {}
        self.nena_bins = int(nena_bins)

        # NeNA state: fine histogram of d < r_max + the number of all pairs (incl. d >= r_max)
        self.fine_bin = float(nena_fine_bin_nm)
        self.fine_counts = np.zeros(int(math.ceil(self.r_max / self.fine_bin)), np.int64)
        self.n_pairs = 0
        self._nena_popt = None
        self._tail = None             # newest frame seen so far: (frame, x, y, chain sum x, sum y, count)

        # FRC state
        self.origin = tuple(float(v) for v in origin_nm)
        self.fov = None
        self.pixel = None
        self._fov_fixed = fov_nm is not None
        self.canvas = None            # float32 [splits, 2, n, n], Hann-windowed
        self._win = (0.5 * (1 - np.cos(2 * np.pi * np.arange(self.n) / (self.n - 1)))).astype(np.float32)
        ky = np.fft.fftfreq(self.n) * self.n
        kx = np.fft.rfftfreq(self.n) * self.n
        self._n_rings = self.n // 2
        self._ring = np.minimum(np.rint(np.sqrt(ky[:, None] ** 2 + kx[None, :] ** 2)),
                                self._n_rings).astype(np.int32)
        self._wcol = np.full(kx.size, 2.0)   # rfft columns 1..n/2-1 stand for two spectrum columns
        self._wcol[0] = self._wcol[-1] = 1.0

        # every raw localization (for re-analysis), and what the FRC canvases hold
        # (blink-merged if frc_merge_nm > 0), kept for canvas re-renders
        self.locs = GrowableColumns({'frame': (np.int64, ()), 'x': (np.float64, ()), 'y': (np.float64, ())})
        self.frc_locs = GrowableColumns({'frame': (np.int64, ()), 'x': (np.float64, ()), 'y': (np.float64, ()),
                                         'n_merged': (np.int32, ()), 'halves': (np.int8, (self.n_splits,))})
        self.last_frame = -1
        self._last_add_ms = 0.0
        if fov_nm is not None:
            self._set_canvas(float(fov_nm))

    # ------------------------------------------------------------------ public API
    def warmup(self):
        """Compile the numba kernels on toy data and import torch (a few ms once cached on disk)."""
        if HAVE_NUMBA:
            v = np.array([0.0, 1.0, 0.5, 2.0])
            nn = np.full(4, -1, np.int64)
            _nn_next_frame(v, v, np.array([0, 1], np.int64), np.array([0, 2, 4], np.int64), 10.0, np.empty(4), nn)
            _merge_chains(nn, v, 1.0, v.copy(), v.copy(), np.ones(4, np.int64), np.ones(4, np.bool_))
            _scatter_add(v, v, np.zeros((1, 4), np.int8), 0.0, 0.0, 1.0, 4, np.ones(4, np.float32),
                         np.zeros((2, 4, 4), np.float32))
            _ring_sums(np.zeros((2, 4, 3), np.complex64), np.zeros((4, 3), np.int32), np.ones(3), 2, 2)
        # plan the FFT for the real canvas now if its size is known (FFTW_MEASURE takes seconds)
        self._fft(self.canvas if self.canvas is not None else np.zeros((2, 8, 8), np.float32))

    def add(self, frame, x, y):
        """Add one chunk. Chunks must arrive in frame order; one frame may straddle two chunks."""
        t0 = time.perf_counter()
        frame = np.asarray(frame, np.int64)
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        if frame.size == 0:
            return
        if np.any(np.diff(frame) < 0):
            o = np.argsort(frame, kind='stable')
            frame, x, y = frame[o], x[o], y[o]
        if frame[0] < self.last_frame:
            raise ValueError(f'chunk starts at frame {frame[0]}, but frame {self.last_frame} was already seen')
        if self._finalized:
            raise RuntimeError('add() after finalize()')
        self.locs.append(frame=frame, x=x, y=y)
        merged = self._add_nena(frame, x, y)
        if merged is None:
            self._add_frc_locs(frame, x, y, np.ones(frame.size, np.int32))
        else:
            self._add_frc_locs(*merged)
        self.last_frame = int(frame[-1])
        self._last_add_ms = (time.perf_counter() - t0) * 1e3

    def finalize(self):
        """End of acquisition: send the blink chains still open in the newest frame to the FRC.
        No-op without merging. No add() may follow."""
        if self._finalized:
            return
        self._finalized = True
        if self.frc_merge_nm > 0 and self._tail is not None:
            tf, _, _, sx, sy, cnt = self._tail
            self._add_frc_locs(tf, sx / cnt, sy / cnt, cnt.astype(np.int32))

    def update(self) -> NeNAFRCResult:
        t = {'add': self._last_add_ms}
        t0 = time.perf_counter()
        nena, nena_err = self.nena()
        t['nena_fit'] = (time.perf_counter() - t0) * 1e3
        t0 = time.perf_counter()
        per_split = self.frc()
        t['frc'] = (time.perf_counter() - t0) * 1e3
        t['total'] = sum(t.values())
        good = [v for v in per_split if np.isfinite(v)]
        frc = float(np.mean(good)) if good else float('nan')
        frc_sd = float(np.std(good)) if len(good) > 1 else float('nan')
        return NeNAFRCResult(self.locs.size, self.last_frame, nena, nena_err, self.n_pairs, frc, frc_sd,
                             per_split, t, self.frc_locs.size)

    # ------------------------------------------------------------------ NeNA
    def nena_histogram(self):
        """webSMLM's histogram rebuilt from the fine state -> (bin centres, counts)."""
        if self.n_pairs < 50:
            return None, None
        cum = np.cumsum(self.fine_counts)
        k = int(math.floor(self.n_pairs * 0.25))       # rank of the 25th percentile among ALL pairs
        if k >= cum[-1]:
            raise RuntimeError('25th-percentile NN distance exceeds r_max; raise r_max_nm')
        p25 = (np.searchsorted(cum, k + 1) + 0.5) * self.fine_bin
        max_d = max(20.0, 4 * p25)
        bin_w = max_d / self.nena_bins
        fine_c = (np.arange(self.fine_counts.size) + 0.5) * self.fine_bin
        keep = fine_c < max_d
        y = np.bincount((fine_c[keep] / bin_w).astype(np.int64), weights=self.fine_counts[keep],
                        minlength=self.nena_bins)[:self.nena_bins]
        return (np.arange(self.nena_bins) + 0.5) * bin_w, y

    def nena(self):
        centers, y = self.nena_histogram()
        if centers is None:
            return float('nan'), float('nan')
        try:
            s, e, popt = fit_nena(centers, y, self._nena_popt)
        except (RuntimeError, ValueError):
            try:
                s, e, popt = fit_nena(centers, y, None)   # cold restart from webSMLM's guess
            except (RuntimeError, ValueError):
                self._last_nena = (centers, y, None)
                return float('nan'), float('nan')
        self._nena_popt = popt
        self._last_nena = (centers, y, popt)             # for save_debug_plots()
        return s, e

    def _add_nena(self, frame, x, y):
        """NN search over (tail frame + chunk): feeds the NeNA histogram and, with merging
        on, the blink chains. Returns the chains that ended, as (frame, x, y, n_merged), or
        None when merging is off."""
        n_new = frame.size
        if self._tail is not None:
            tf, tx, ty, tsx, tsy, tcnt = self._tail
            frame = np.concatenate((tf, frame))
            x = np.concatenate((tx, x))
            y = np.concatenate((ty, y))
        else:
            tsx = tsy = np.empty(0)
            tcnt = np.empty(0, np.int64)
        uniq, starts = _frame_index(frame)
        d, nn = nn_next_frame(x, y, frame, self.r_max, (uniq, starts))
        # The newest frame's successor has not arrived yet: keep it as the tail and
        # let the next chunk count its pairs (and extend its chains).
        cut = starts[-2]
        # every loc of a frame whose successor exists has a neighbour (maybe beyond r_max)
        has_next = uniq[1:] == uniq[:-1] + 1
        self.n_pairs += int(np.diff(starts)[:-1][has_next].sum())
        dn = d[:cut]
        dn = dn[dn < self.r_max]
        if dn.size:
            idx = np.minimum((dn / self.fine_bin).astype(np.int64), self.fine_counts.size - 1)
            self.fine_counts += np.bincount(idx, minlength=self.fine_counts.size)

        merged = None
        if self.frc_merge_nm > 0:
            # tail locs carry their chain's running sums; new locs start a chain of one
            k = frame.size - n_new
            sx = np.concatenate((tsx, x[k:]))
            sy = np.concatenate((tsy, y[k:]))
            cnt = np.concatenate((tcnt, np.ones(n_new, np.int64)))
            ended = merge_chains(nn, d, self.frc_merge_nm, sx, sy, cnt)
            ended[cut:] = False                          # may still continue into the next chunk
            merged = (frame[ended], sx[ended] / cnt[ended], sy[ended] / cnt[ended], cnt[ended].astype(np.int32))
            self._tail = (frame[cut:], x[cut:], y[cut:], sx[cut:], sy[cut:], cnt[cut:])
        else:
            self._tail = (frame[cut:], x[cut:], y[cut:], None, None, None)
        return merged

    # ------------------------------------------------------------------ FRC
    def frc(self):
        """FRC resolution (nm) per split."""
        if self.canvas is None:
            return [float('nan')] * self.n_splits
        F = self._fft(self.canvas)                       # [1 + splits, n, n//2+1] complex64
        sums = self._ring_sums(F)                        # [splits, rings, 3]
        freq = np.arange(self._n_rings) / self.fov
        out, raws, smooths = [], [], []
        for s in range(self.n_splits):
            num, d1, d2 = sums[s, :, 0], sums[s, :, 1], sums[s, :, 2]
            with np.errstate(invalid='ignore', divide='ignore'):
                c = np.nan_to_num(num / np.sqrt(d1 * d2))
            sm = self._smooth_frc(c)
            raws.append(c)
            smooths.append(sm)
            below = np.flatnonzero(sm[3:] < self.threshold)
            if below.size == 0:
                out.append(float('nan'))                # finer than Nyquist (2 x pixel)
                continue
            i = 3 + below[0]
            v0, v1 = sm[i - 1], sm[i]
            fc = freq[i - 1] + (freq[i] - freq[i - 1]) * (self.threshold - v0) / (v1 - v0) if v1 != v0 else freq[i]
            out.append(float(1.0 / fc) if fc > 0 else float('nan'))
        self._last_frc = (freq, raws, smooths, out)      # for save_debug_plots()
        return out

    def _smooth_frc(self, c):
        """Smooth the FRC curve before looking for the 1/7 crossing.
        'gauss' (default): Gaussian of frc_smooth_sigma (1/nm, converted to rings for this
            FOV). With light or no smoothing, noise dips below 1/7 early and the *first*
            crossing lands there: on the test file raw -> 25.2 +- 0.55 nm, 1-2-1 -> 24.6
            +- 0.6, gauss 4..25 rings -> 23.1 +- 0.1 (a plateau, so the width barely matters).
        'websmlm': webSMLM's 1-2-1 filter - use to reproduce webSMLM's numbers exactly.
        'none': the raw curve."""
        if self.frc_smoothing == 'none':
            return c
        if self.frc_smoothing == 'websmlm':
            sm = c.copy()
            sm[1:-1] = (c[:-2] + 2 * c[1:-1] + c[2:]) / 4
            return sm
        if self.frc_smoothing == 'gauss':
            from scipy.ndimage import gaussian_filter1d
            sigma_rings = self.frc_smooth_sigma * self.fov      # ring spacing is 1/fov
            return gaussian_filter1d(c, sigma_rings, mode='nearest') if sigma_rings > 0 else c
        raise ValueError(f'unknown frc_smoothing {self.frc_smoothing!r}')

    # ------------------------------------------------------------------ debug output
    def frc_snapshot(self):
        """The last update's FRC, averaged over the splits (smoothed curve) - one entry of
        the history plotted by plot_frc_history(). None before the first frc()."""
        if getattr(self, '_last_frc', None) is None:
            return None
        freq, _, smooths, res = self._last_frc
        good = [r for r in res if np.isfinite(r)]
        return {'last_frame': self.last_frame, 'n_locs': self.locs.size, 'n_frc_locs': self.frc_locs.size,
                'freq': freq, 'curve': np.mean(smooths, axis=0),
                'frc_nm': float(np.mean(good)) if good else float('nan'),
                'frc_err_nm': float(np.std(good)) if len(good) > 1 else float('nan')}

    def save_debug_plots(self, folder, tag=''):
        """Write the state behind the last update() to `folder` as PNGs:
        <tag>_frc.png (FRC curve per split, raw + smoothed, 1/7 threshold, crossings),
        <tag>_nena.png (NeNA histogram, full fit and its signal term),
        <tag>_frc_image.png (the summed image both splits come from, windowed as fed to the FFT).
        Not timed and not needed for the estimate - call it after update()."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        pre = f'{tag}_' if tag else ''
        title = f'{self.locs.size:,} locs, up to frame {self.last_frame}'

        if getattr(self, '_last_frc', None) is not None:
            freq, raws, smooths, res = self._last_frc
            fig, ax = plt.subplots(figsize=(7, 4.5))
            for s, (c, sm, r) in enumerate(zip(raws, smooths, res)):
                line, = ax.plot(freq, sm, lw=1.5, label=f'split {s + 1}: {r:.2f} nm' if np.isfinite(r) else
                                f'split {s + 1}: no crossing')
                ax.plot(freq, c, lw=0.6, alpha=0.35, color=line.get_color())
                if np.isfinite(r):
                    ax.axvline(1 / r, color=line.get_color(), ls=':', lw=1)
            ax.axhline(self.threshold, color='k', ls='--', lw=1, label='1/7')
            ax.set_ylim(-0.2, 1.05)
            ax.set_xlim(0, freq[-1])
            ax.set_xlabel('spatial frequency (1/nm)')
            ax.set_ylabel('FRC')
            good = [r for r in res if np.isfinite(r)]
            ax.set_title(f'FRC {np.mean(good):.2f} nm - {title}' if good else f'FRC - {title}', fontsize=10)
            ax.legend(fontsize=8)
            sec = ax.secondary_xaxis('top', functions=(lambda q: 1 / np.maximum(q, 1e-9),
                                                       lambda r: 1 / np.maximum(r, 1e-9)))
            sec.set_xlabel('resolution (nm)')
            sec.set_xticks([100, 50, 30, 20, 15])
            fig.tight_layout()
            fig.savefig(folder / f'{pre}frc.png', dpi=120)
            plt.close(fig)

        if getattr(self, '_last_nena', None) is not None:
            centers, y, popt = self._last_nena
            bw = centers[1] - centers[0]
            fig, ax = plt.subplots(figsize=(7, 4.5))
            ax.bar(centers, y, width=bw, color='#9fb4d8', label=f'NN distances ({self.n_pairs:,} pairs)')
            if popt is not None:
                xx = np.linspace(0, centers[-1] + bw / 2, 400)
                ax.plot(xx, _nena_model(xx, *popt), color='#d1242f', lw=2, label='fit')
                ax.plot(xx, popt[0] * _S(xx, popt[1]), color='#0a7d32', ls='--', lw=1.4,
                        label=f'signal term, sigma = {popt[1]:.2f} nm')
            ax.set_xlabel('NN distance, frame f -> f+1 (nm)')
            ax.set_ylabel('pairs per bin')
            ax.set_title(f'NeNA - {title}', fontsize=10)
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig(folder / f'{pre}nena.png', dpi=120)
            plt.close(fig)

        if self.canvas is not None:
            img = self.canvas[0]                        # total = half A + half B, Hann-windowed
            nz = img[img > 0]
            vmax = float(np.percentile(nz, 99.5)) if nz.size else 1.0
            ext = [self.origin[0], self.origin[0] + self.fov, self.origin[1] + self.fov, self.origin[1]]
            fig, ax = plt.subplots(figsize=(8, 8))
            ax.imshow(img, cmap='magma', vmin=0, vmax=vmax, extent=ext, interpolation='nearest')
            ax.set_xlabel('x (nm)')
            ax.set_ylabel('y (nm)')
            ax.set_title(f'FRC input: summed halves, Hann-windowed, {self.n}^2 at {self.pixel:.2f} nm/px\n{title}',
                         fontsize=10)
            fig.tight_layout()
            fig.savefig(folder / f'{pre}frc_image.png', dpi=150)
            plt.close(fig)

    def _assign_halves(self, frame):
        if self.split == 'random':
            return self.rng.integers(0, 2, (frame.size, self.n_splits), dtype=np.int8)
        if self.split == 'frameblock':
            return ((frame // self.block_frames) % 2).astype(np.int8)[:, None]
        if self.split == 'oddeven':
            return (frame % 2).astype(np.int8)[:, None]
        raise ValueError(self.split)

    def _set_canvas(self, fov_nm):
        self.fov = fov_nm
        self.pixel = fov_nm / self.n
        if self.canvas is None:
            # plane 0 = all locs, plane 1+s = half A of split s (half B = total - A, by FFT linearity:
            # K splits cost K+1 FFTs instead of 2K)
            self.canvas = np.zeros((1 + self.n_splits, self.n, self.n), np.float32)
        else:
            self.canvas.fill(0)

    def _add_frc_locs(self, frame, x, y, n_merged):
        """Assign halves to FRC localizations, store them, render them into the canvases."""
        if frame.size == 0:
            return
        halves = self._assign_halves(frame)
        self.frc_locs.append(frame=frame, x=x, y=y, n_merged=n_merged, halves=halves)
        self._add_frc(x, y, halves)

    def _add_frc(self, x, y, halves):
        if self.canvas is None:
            # origin stays put (camera coordinates are >= 0); only the extent adapts
            ext = max(x.max() - self.origin[0], y.max() - self.origin[1])
            self._set_canvas(ext * 1.02)
            self._render(self.frc_locs['x'], self.frc_locs['y'], self.frc_locs['halves'])
            return
        ext = max(x.max() - self.origin[0], y.max() - self.origin[1])
        if not self._fov_fixed and ext >= self.fov:
            self._set_canvas(max(ext * 1.02, self.fov * 1.5))
            self._render(self.frc_locs['x'], self.frc_locs['y'], self.frc_locs['halves'])
            return
        self._render(x, y, halves)

    def _render(self, x, y, halves):
        halves_t = np.ascontiguousarray(halves.T)       # [splits, n_locs]
        if HAVE_NUMBA:
            _scatter_add(x, y, halves_t, self.origin[0], self.origin[1], self.pixel, self.n, self._win, self.canvas)
            return
        n = self.n
        ix = np.clip(((x - self.origin[0]) / self.pixel).astype(np.int64), 0, n - 1)
        iy = np.clip(((y - self.origin[1]) / self.pixel).astype(np.int64), 0, n - 1)
        w = self._win[iy] * self._win[ix]
        flat = iy * n + ix
        self.canvas[0] += np.bincount(flat, weights=w, minlength=n * n).astype(np.float32).reshape(n, n)
        for s in range(self.n_splits):
            a = halves_t[s] == 0
            self.canvas[1 + s] += np.bincount(flat[a], weights=w[a], minlength=n * n).astype(np.float32).reshape(n, n)

    def _fft(self, img):
        """Batched rfft2 over the last two axes. 'auto': torch if the process already
        imported it (it costs ~9 s to import), else pyfftw with a plan cached per shape
        (as fast as torch here), else torch, else scipy (2-4x slower)."""
        fn = self._fft_plans.get(img.shape)
        if fn is None:
            fn = self._fft_plans[img.shape] = self._make_fft(img)
        return fn(img)

    def _make_fft(self, img):
        import sys
        b = self.fft_backend
        if b == 'torch' or (b == 'auto' and 'torch' in sys.modules):
            torch = _get_torch()
            if torch is not None:
                return lambda a: torch.fft.rfft2(torch.from_numpy(a)).numpy()
        if b in ('auto', 'pyfftw'):
            try:
                import pickle
                import tempfile
                import pyfftw
                import pyfftw.builders
                # FFTW_MEASURE planning costs seconds; persist the "wisdom" so it is paid once per machine
                wisdom = Path(tempfile.gettempdir()) / 'glados_nena_frc_fftw_wisdom.pkl'
                try:
                    pyfftw.import_wisdom(pickle.loads(wisdom.read_bytes()))
                except (OSError, ValueError, pickle.UnpicklingError):
                    pass
                plan = pyfftw.builders.rfft2(pyfftw.empty_aligned(img.shape, np.float32), axes=(-2, -1),
                                             threads=N_CORES, planner_effort='FFTW_MEASURE')
                try:
                    wisdom.write_bytes(pickle.dumps(pyfftw.export_wisdom()))
                except OSError:
                    pass
                # the returned array is the plan's own output buffer, overwritten on the next call
                return lambda a: plan(a)
            except ImportError:
                pass
        if b == 'auto':
            torch = _get_torch()
            if torch is not None:
                return lambda a: torch.fft.rfft2(torch.from_numpy(a)).numpy()
        return lambda a: sfft.rfft2(a, workers=-1)

    def _ring_sums(self, F):
        """-> [splits, rings, 3] ring sums of Re(A B*), |A|^2, |B|^2."""
        if HAVE_NUMBA:
            return _ring_sums(F, self._ring, self._wcol, self._n_rings, N_THREADS)[:, :-1]
        w = np.broadcast_to(self._wcol, self._ring.shape).ravel()
        idx = self._ring.ravel()
        out = np.empty((self.n_splits, self._n_rings, 3))
        for s in range(self.n_splits):
            A, B = F[1 + s], F[0] - F[1 + s]
            for k, v in enumerate((A.real * B.real + A.imag * B.imag, A.real ** 2 + A.imag ** 2,
                                   B.real ** 2 + B.imag ** 2)):
                out[s, :, k] = np.bincount(idx, weights=v.ravel() * w, minlength=self._n_rings + 1)[:-1]
        return out


def plot_frc_history(history, path, threshold=1 / 7):
    """One figure with the split-averaged, smoothed FRC curve of every update, coloured
    by how far the acquisition had got, with each update's resolution marked."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    history = [h for h in history if h is not None]
    if not history:
        return
    frames = np.array([h['last_frame'] for h in history], float)
    cmap = plt.get_cmap('viridis')
    norm = matplotlib.colors.Normalize(frames.min(), frames.max() if frames.max() > frames.min() else frames.min() + 1)
    fig, ax = plt.subplots(figsize=(8, 5))
    for h in history:
        col = cmap(norm(h['last_frame']))
        ax.plot(h['freq'], h['curve'], color=col, lw=1.2)
        if np.isfinite(h['frc_nm']):
            ax.plot(1 / h['frc_nm'], threshold, 'o', color=col, ms=4, mec='k', mew=0.4)
    ax.axhline(threshold, color='k', ls='--', lw=1, label='1/7')
    ax.set_ylim(-0.2, 1.05)
    ax.set_xlim(0, max(h['freq'][-1] for h in history))
    ax.set_xlabel('spatial frequency (1/nm)')
    ax.set_ylabel('FRC (mean of splits, smoothed)')
    first, last = history[0], history[-1]
    ax.set_title(f'FRC per update: {first["frc_nm"]:.2f} nm at frame {first["last_frame"]} -> '
                 f'{last["frc_nm"]:.2f} nm at frame {last["last_frame"]} ({len(history)} updates)', fontsize=10)
    sec = ax.secondary_xaxis('top', functions=(lambda q: 1 / np.maximum(q, 1e-9), lambda r: 1 / np.maximum(r, 1e-9)))
    sec.set_xlabel('resolution (nm)')
    sec.set_xticks([100, 50, 30, 20, 15])
    fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, label='last frame included')
    ax.legend(fontsize=8, loc='upper right')
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_frc_vs_emitters(history, path, merge_nm=0.0):
    """FRC resolution +- SD over splits against the number of emitters that went into it
    (blink-merged localizations if merging is on), one point per update."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    history = [h for h in history if h is not None]
    if not history:
        return
    n = np.array([h['n_frc_locs'] for h in history], float)
    r = np.array([h['frc_nm'] for h in history])
    e = np.array([h['frc_err_nm'] for h in history])
    raw = np.array([h['n_locs'] for h in history], float)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.errorbar(n, r, yerr=np.nan_to_num(e), fmt='o-', ms=4, capsize=3, lw=1.2, color='#0969da',
                label='FRC resolution +- SD over splits')
    ax.set_xlabel('emitters in FRC' + (f' (localizations merged within {merge_nm:g} nm in consecutive frames)'
                                      if merge_nm > 0 else ' (localizations)'))
    ax.set_ylabel('FRC resolution (nm)')
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlim(n.min() / 1.3, n.max() * 1.3)
    # a narrow resolution range spans less than a decade: label plain numbers, not 10^x
    ax.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.yaxis.set_minor_formatter(matplotlib.ticker.ScalarFormatter())
    if merge_nm > 0:
        # raw = emitters x (raw/emitters ratio), the ratio interpolated in log space and held
        # constant beyond the data, so the mapping stays monotonic across the whole axis
        ln, lr, lq = np.log(n), np.log(raw), np.log(raw / n)
        lv = lambda v: np.log(np.maximum(v, 1e-9))
        sec = ax.secondary_xaxis('top', functions=(lambda v: v * np.exp(np.interp(lv(v), ln, lq)),
                                                   lambda v: v / np.exp(np.interp(lv(v), lr, lq))))
        sec.set_xlabel('raw localizations')
    ax.set_title(f'FRC {r[-1]:.2f} +- {np.nan_to_num(e[-1]):.2f} nm with {int(n[-1]):,} emitters', fontsize=10)
    ax.grid(alpha=0.3, which='both')
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ============================================================================ CLI demo
def load_csv(path):
    import pandas as pd
    header = pd.read_csv(path, nrows=0).columns.tolist()
    pick = lambda *names: next(n for n in names if n in header)
    cols = [pick('frame', 'Frame', 't'), pick('x [nm]', 'x_nm', 'x'), pick('y [nm]', 'y_nm', 'y')]
    try:
        df = pd.read_csv(path, usecols=cols, engine='pyarrow')
    except (ImportError, ValueError):
        df = pd.read_csv(path, usecols=cols)
    df = df.sort_values(cols[0], kind='stable')
    return df[cols[0]].to_numpy(np.int64), df[cols[1]].to_numpy(np.float64), df[cols[2]].to_numpy(np.float64)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--csv', type=Path, default=HERE / 'webSMLM_simulated_locs.csv')
    p.add_argument('--chunk-frames', type=int, default=1000)
    p.add_argument('--frc-splits', type=int, default=3, help='independent random splits (webSMLM: 3)')
    p.add_argument('--split', default='random', choices=['random', 'frameblock', 'oddeven'])
    p.add_argument('--block-frames', type=int, default=10)
    p.add_argument('--n-pixels', type=int, default=2048)
    p.add_argument('--r-max', type=float, default=150.0)
    p.add_argument('--grow-fov', action='store_true',
                   help="don't pre-set the FOV from the file (simulates an unknown FOV; canvas grows)")
    p.add_argument('--frc-smoothing', default='gauss', choices=['gauss', 'websmlm', 'none'],
                   help="curve smoothing before the 1/7 crossing: gauss (default), websmlm (1-2-1, "
                        "reproduces webSMLM's numbers) or none")
    p.add_argument('--frc-smooth-sigma', type=float, default=4e-4,
                   help='Gaussian sigma in 1/nm (default 4e-4 = ~5 rings on a 12.5 um FOV)')
    p.add_argument('--frc-merge-nm', type=float, default=10.0,
                   help='FRC only: merge localizations in consecutive frames closer than this (0 = off)')
    p.add_argument('--debug', action='store_true',
                   help='save FRC curves, NeNA histogram+fit and the summed FRC image per update '
                        'into a new debug_<timestamp> folder (not included in the timings)')
    p.add_argument('--debug-dir', type=Path, default=HERE, help='parent folder for the debug folder')
    p.add_argument('--debug-every', type=int, default=1, help='save every N-th update (the last is always saved)')
    args = p.parse_args(argv)
    debug_dir = None
    if args.debug:
        debug_dir = args.debug_dir / time.strftime('debug_%Y%m%d_%H%M%S')
        debug_dir.mkdir(parents=True, exist_ok=False)
        print(f'debug output -> {debug_dir}')

    t0 = time.perf_counter()
    frame, x, y = load_csv(args.csv)
    print(f'loaded {x.size} locs, frames {frame.min()}..{frame.max()} in {(time.perf_counter() - t0) * 1e3:.0f} ms')

    # In a live acquisition the camera FOV is known up front. For the CSV we take the
    # data extent the way webSMLM does (origin at the minimum, extent x1.02), so the
    # final streamed FRC is the one webSMLM would compute on the same localizations.
    geom = {}
    if not args.grow_fov:
        origin = (float(x.min()), float(y.min()))
        geom = dict(origin_nm=origin, fov_nm=max(x.max() - origin[0], y.max() - origin[1]) * 1.02)
    make = lambda: IncrementalNeNAFRC(r_max_nm=args.r_max, n_pixels=args.n_pixels, frc_splits=args.frc_splits,
                                      split=args.split, block_frames=args.block_frames,
                                      frc_smoothing=args.frc_smoothing, frc_smooth_sigma=args.frc_smooth_sigma,
                                      frc_merge_nm=args.frc_merge_nm, **geom)
    est = make()
    t0 = time.perf_counter()
    est.warmup()
    print(f'warm-up (numba JIT/cache load, FFT plan/wisdom load): {(time.perf_counter() - t0) * 1e3:.0f} ms')
    print(f'FRC canvas {est.n}^2 x {est.n_splits} split(s)'
          + (f' at {est.pixel:.2f} nm/px' if est.pixel else ' (sized from the first chunk)') + '\n')

    print(f'FRC blink merging: ' + (f'< {est.frc_merge_nm:g} nm in consecutive frames' if est.frc_merge_nm else 'off'))
    print(f'{"frames":>13} {"locs":>8} {"FRC locs":>8} {"NeNA [nm]":>14} {"FRC [nm]":>15} {"STOP?":>8} | '
          f'{"add":>5} {"fit":>5} {"frc":>6} {"total":>6} ms')
    bounds = np.searchsorted(frame, np.arange(frame.min(), frame.max() + args.chunk_frames, args.chunk_frames))
    totals = []
    res = None
    chunks = [(a, b) for a, b in zip(bounds[:-1], bounds[1:]) if a != b]
    frc_history = []
    for k, (a, b) in enumerate(chunks):
        est.add(frame[a:b], x[a:b], y[a:b])
        if k == len(chunks) - 1:
            est.finalize()                               # end of acquisition: flush open blink chains
        res = est.update()
        t = res.timings_ms
        totals.append(t['total'])
        
        #Checking if we should stop:
        M_factor = 4
        w=h=12.5 #um
        required_nr_locs = (2.71/(M_factor*3*3.141592))/((res.nena_nm/1000)**2)*w*h
        if res.n_locs > required_nr_locs:
            stopping = True
        else:
            stopping=False
        
        print(f'{frame[a]:>6}-{frame[b - 1]:<6} {res.n_locs:>8} {res.n_frc_locs:>8} {res.nena_nm:>6.2f} +- '
              f'{res.nena_err_nm:<4.2f} {res.frc_nm:>6.2f} +- {res.frc_err_nm:<5.2f}  {stopping:<5} | {t["add"]:>5.1f} '
              f'{t["nena_fit"]:>5.1f} {t["frc"]:>6.1f} {t["total"]:>6.1f}')
        if debug_dir is not None:
            frc_history.append(est.frc_snapshot())       # every update, whatever --debug-every says
            if k % max(args.debug_every, 1) == 0 or k == len(chunks) - 1:
                est.save_debug_plots(debug_dir, tag=f'{k + 1:03d}_frames{frame[0]}-{frame[b - 1]}')
    if debug_dir is not None:
        plot_frc_history(frc_history, debug_dir / 'frc_all_updates.png', est.threshold)
        plot_frc_vs_emitters(frc_history, debug_dir / 'frc_vs_emitters.png', est.frc_merge_nm)

    totals = np.array(totals)
    print(f'\nper-update latency: mean {totals.mean():.1f} ms, median {np.median(totals):.1f} ms, '
          f'max {totals.max():.1f} ms over {totals.size} updates')

    # Consistency check: one-shot on the full table, handing out the streamed run's split
    # bits in the same order, must give the same NeNA state and the same merged FRC input
    # exactly, and the same FRC (up to float32 summation order).
    one = make()
    one.warmup()
    streamed_halves, pos = est.frc_locs['halves'], [0]

    def replay_halves(f):
        h = streamed_halves[pos[0]:pos[0] + f.size]
        pos[0] += f.size
        return h
    one._assign_halves = replay_halves
    t0 = time.perf_counter()
    one.add(frame, x, y)
    one.finalize()
    ref = one.update()
    one_ms = (time.perf_counter() - t0) * 1e3
    same_frc_in = (one.frc_locs.size == est.frc_locs.size
                   and np.array_equal(one.frc_locs['x'], est.frc_locs['x'])
                   and np.array_equal(one.frc_locs['y'], est.frc_locs['y']))
    print(f'one-shot on all {x.size} locs in {one_ms:.0f} ms: NeNA {ref.nena_nm:.3f}, FRC {ref.frc_nm:.3f} | '
          f'NeNA state identical: {np.array_equal(one.fine_counts, est.fine_counts) and one.n_pairs == est.n_pairs}, '
          f'merged FRC input identical: {same_frc_in}, '
          f'|dNeNA| {abs(ref.nena_nm - res.nena_nm):.1e} nm, |dFRC| {abs(ref.frc_nm - res.frc_nm):.1e} nm')
    if est.frc_merge_nm:
        nm = est.frc_locs['n_merged']
        print(f'blink merging: {x.size:,} locs -> {nm.size:,} FRC locs ({x.size / nm.size:.2f} locs per chain, '
              f'longest chain {nm.max()} frames)')
    print(f'\nFINAL  NeNA {res.nena_nm:.2f} +- {res.nena_err_nm:.2f} nm   (webSMLM 6.5 +- 0.1 nm, ~10 s)')
    print(f'FINAL  FRC  {res.frc_nm:.2f} +- {res.frc_err_nm:.2f} nm   (webSMLM 24.4 +- 0.4 nm, ~30 s)'
          f'   per split: {", ".join(f"{v:.2f}" for v in res.frc_per_split)}')


if __name__ == '__main__':
    main()
