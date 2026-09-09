import datetime
import gc
import importlib
import json
import logging
import os
from pathlib import Path
import sys
import time
import weakref
from collections import deque
from threading import Event, RLock, Thread, get_native_id

import appdirs
import napari
import numpy as np
import useq
from napari.qt import thread_worker
from PyQt5.QtCore import QObject, Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractButton,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
)
from qtpy.QtWidgets import QMainWindow, QScrollArea, QVBoxLayout, QWidget

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from pycromanager import Acquisition, multi_d_acquisition_events

import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
import glados_pycromanager.GUI.napariGlados as napariGlados
import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.Core.MDAGlados import MDAGlados
from glados_pycromanager.GUI.custom_widget_ui import (
    Ui_CustomDockWidget,  # Import the generated UI module
)
from glados_pycromanager.GUI.frame_ring import DEFAULT_CAPACITY as FRAME_RING_CAPACITY
from glados_pycromanager.GUI.frame_ring import FrameRing
from glados_pycromanager.GUI.frame_writer import ZarrFrameWriter
from glados_pycromanager.GUI.MMcontrols import microManagerControlsUI
from glados_pycromanager.GUI.napariHelperFunctions import InitateNapariUI, getLayerIdFromName, moveLayerToTop
from glados_pycromanager.GUI.utils import cleanUpTemporaryFiles

    # from glados_pycromanager.GUI.sharedFunctions import Shared_data #Gives circular import error in sharedFunctions

def _connect_mda_signal_direct(mda_signal, slot):
    """Connect a core.mda.events.* callback with an explicit Qt.DirectConnection.

    pymmcore-plus auto-selects a Qt-based (PyQt5) signaler for core.mda.events
    whenever a QApplication is running, which is always true in this GUI app.
    These connect() calls happen inside a napari @thread_worker (a QThreadPool
    worker thread with no Qt event loop of its own), so under the default
    Qt.AutoConnection the slot invocation is queued for that thread and is
    never dispatched — nothing pumps it, and it silently never fires (the
    MDA/hardware acquisition proceeds independently regardless, so nothing in
    the log looks wrong). DirectConnection makes the callback run synchronously
    on the emitting thread instead, which is both correct and avoids any
    polling overhead. Applies equally to frameReady, sequenceStarted,
    sequenceFinished, sequenceCanceled, etc. — all live on the same signaler.

    Falls back to a plain connect() for the psygnal backend (used when no Qt
    app is running, e.g. in tests), which doesn't accept a `type` kwarg and
    already invokes synchronously in the emitting thread.
    """
    try:
        return mda_signal.connect(slot, type=Qt.DirectConnection)
    except TypeError:
        return mda_signal.connect(slot)


def _get_cached_dimensions(shared_data):
    """Return getDimensionsFromAcqData result, recomputing only when _mdaModeParams changes.

    Keyed on `shared_data._mdaModeParamsGeneration`, a counter the
    `_mdaModeParams` setter bumps on every assignment (T-D5). The key used to be
    `id(params)`, which is not an acquisition identity at all: CPython reuses the
    addresses of freed objects, so once the previous acquisition's event list was
    released a new one could land on the same address and the cache would return
    the *previous* acquisition's dimension map. sliceTuple, the zarr shape and the
    napari dims stepping all derive from it.

    The generation is read before `_mdaModeParams`, so a cache hit does not touch
    the property at all -- which also avoids triggering its lazy
    useq.MDASequence -> pycromanager-event-list conversion for a value already
    summarised here.
    """
    generation = shared_data._mdaModeParamsGeneration
    cached = getattr(shared_data, '_dims_cache', None)
    # Compare rather than test for absence: getDimensionsFromAcqData legitimately
    # returns None (empty event list, or a malformed one it warns about), so a
    # cached None must not read as "nothing cached yet".
    if cached is None or cached[0] != generation:
        result = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
        shared_data._dims_cache = (generation, result)
        return result
    return cached[1]


#: Metadata key stamped by `_try_write_frame_to_zarr` on a frame it has already
#: written into the multiDstack store, holding the slice index it wrote to. The
#: display path reads it to skip a second, identical write of the same frame
#: (T-D2). Absent for backends whose acquisition path does no zarr write (both
#: pycromanager `image_process_fn` / `image_saved_fn` paths), and absent if that
#: write failed -- in both cases the display path writes the frame itself.
ZARR_WRITTEN_SLICE_KEY = '_gladosZarrWrittenSlice'


#: Output-handler suffixes pymmcore-plus infers a writer from. `handler_for_path`
#: dispatches on the extension: '.zarr' -> OMEZarrWriter, '.tif'/'.tiff' ->
#: OMETiffWriter. Anything else raises, so these are not free-form strings.
MMCORE_SAVE_SUFFIXES = {'ome-zarr': '.ome.zarr', 'ome-tiff': '.ome.tiff'}


def mmcore_output_path(shared_data, savefolder, savename):
    """Where pymmcore-plus should write this MDA, or None to acquire unsaved.

    The `MMCORE_PLUS` MDA branch used to ignore the user's Storage folder
    completely: `savefolder`/`savename` were computed and never read, and the
    only copy of the data was the scratch zarr in a `TemporaryDirectory` that
    `release_all_temp_dirs()` deletes on exit. So an MDA on that backend saved
    nothing, anywhere. It has no NDTiff engine of its own, which is why the
    pycromanager branches next to it did not have this problem.

    pymmcore-plus can do the recording itself -- `run_mda(..., output=<path>)`
    picks a writer from the suffix -- which is also the design this project
    wants: the backend records, Glados hooks on. This just builds the path.

    Returns None when the user set no Storage folder, or chose 'none', so
    "acquire without saving" stays reachable.
    """
    fmt = getattr(shared_data.config.mda_config, 'mmcore_save_format', 'ome-zarr')
    suffix = MMCORE_SAVE_SUFFIXES.get(fmt)
    if suffix is None or not savefolder:
        return None
    folder = Path(savefolder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logging.error('Cannot write to Storage folder %s (%s); MDA will not be saved',
                      savefolder, exc)
        return None
    stem = savename or 'MDA'
    # Never overwrite a previous acquisition -- the same reflex pycromanager has
    # when it suffixes a duplicate acquisition name.
    candidate = folder / f'{stem}{suffix}'
    attempt = 1
    while candidate.exists():
        candidate = folder / f'{stem}_{attempt}{suffix}'
        attempt += 1
    return candidate


def _camera_dtype(shared_data):
    """numpy dtype of one camera pixel (uint8 for 8-bit cameras, else uint16).

    Falls back to uint16 -- the common case -- if the core cannot be asked.
    """
    try:
        bytes_per_pixel = shared_data.MILcore.core.getBytesPerPixel()
        return np.uint8 if bytes_per_pixel <= 1 else np.uint16
    except Exception as exc:
        logging.debug('_camera_dtype: falling back to uint16 (%s)', exc)
        return np.uint16


def _create_mda_zarr(shared_data, layer_name, shape, h, w, dtype):
    """Create the multiDstack display store for `layer_name` and register it.

    The single creation site for `shared_data.mdaZarrData` (T-D1). It used to
    have two, and they disagreed: the display-path fallback called `zarr.open()`
    with no `dtype=`, which on zarr 3.x yields a **float64** array, so every
    uint16 camera frame was upcast on write -- 4x the bytes through the
    compressor and on disk, and napari's contrast fast path defeated. Which
    array you ended up with was a race between the two sites.

    `dtype` is therefore required, not defaulted. `shape` is the acquisition's
    non-image dimensions; `h`/`w` are appended as the frame plane. The
    TemporaryDirectory backing the store is owned by shared_data, keyed by layer
    name, so it is not GC'd (and the directory deleted) while zarr is still
    writing or a layer still renders it (T-D7).
    """
    import zarr
    shape = list(shape)
    tmpdir = shared_data.new_zarr_temp_dir(layer_name)
    # `zarr.create_array`, not `zarr.open`: on zarr 3.1.0 `open` cannot set
    # compression at all -- it rejects both `compressor` ("cannot be used for
    # arrays with zarr_format 3") and `compressors` (unexpected keyword). This is
    # a scratch store in a TemporaryDirectory, deleted on exit, so paying Zstd to
    # shrink it is the wrong trade: measured on a 1024x1024 uint16 frame,
    # compressors=None writes at ~9.1 ms/frame against ~12.8 ms compressed, and
    # serves a single slice back to napari in ~2.8 ms against ~7.9 ms, for ~17%
    # more bytes on a disk we are about to throw away.
    array = zarr.create_array(
        store=str(tmpdir.name),
        shape=shape + [h, w],
        # One frame per chunk. Bigger chunks were measured and rejected -- see
        # claude_decisions.md (T-D3): even with perfectly batched whole-chunk
        # writes, 8- and 32-frame chunks were slower to write *and* much slower
        # to read, because napari paints a multiDstack layer by reading one
        # slice out of this very array.
        chunks=tuple([1] * len(shape) + [h, w]),
        dtype=dtype,
        compressors=None,
        overwrite=True,
    )
    shared_data.mdaZarrData[layer_name] = array
    shared_data.allMDAslicesRendered = set()
    logging.debug('_create_mda_zarr: layer=%s shape=%s dtype=%s',
                  layer_name, shape + [h, w], np.dtype(dtype))
    return array


def _slice_safe_to_display(shared_data, arrived_slice):
    """Which slice the viewer should actually be pointed at.

    Since T-D3 the zarr write is queued, not immediate: the frame path can run a
    full writer queue ahead of the disk. Pointing napari at the frame that just
    *arrived* therefore asks it to render slices the writer has not written yet,
    and an unwritten slice in a freshly created store is zeros -- which is
    exactly the "live view is black during the acquisition, perfect once it
    finishes" symptom.

    So follow the writer instead: show the newest slice that has genuinely
    reached disk. Slightly behind live, never black. `arrived_slice` is the
    fallback for every path with no writer running (both pycromanager backends,
    and the inline-write fallback), where the frame is already on disk by the
    time this is reached.
    """
    writer = getattr(shared_data, 'zarrFrameWriter', None)
    if writer is None:
        return arrived_slice
    written = writer.last_written_tag
    if written is None or len(written) != len(arrived_slice):
        # Nothing committed yet, or a store that changed shape under us: the
        # arrived index is the better guess, and it is what the old code did.
        return arrived_slice
    return written


def _get_contrast_frame_counters(shared_data):
    """Per-layer-name frame counters backing the throttled auto-contrast
    refresh (see _maybe_refresh_contrast). Lazily initialized on shared_data,
    same pattern as _dims_cache.
    """
    counters = getattr(shared_data, '_contrast_frame_counters', None)
    if counters is None:
        counters = {}
        shared_data._contrast_frame_counters = counters
    return counters


def _layer_shape_already_validated(shared_data, layerName, layer):
    """True if `layer` was shape-checked against the current acquisition plan.

    The multiDstack display path used to re-derive the plan's dimensions and
    re-compare them against the layer's shape on **every frame**, with a
    `layers.pop()` plus zarr reset waiting on the other side of any mismatch --
    a full teardown, texture re-upload and store re-creation, driven from the
    hot path (T-E3). The shape of an existing layer cannot drift on its own:
    it can only stop matching when the *plan* changes (a new MDA with different
    dimensions) or when the layer object itself is replaced. Both are exactly
    what this cache keys on, so the real check runs once per acquisition
    instead of once per frame.

    Keyed on `_mdaModeParamsGeneration` -- the same counter `_get_cached_dimensions`
    uses, bumped by the `_mdaModeParams` setter -- plus a **weak reference** to
    the validated layer. The weakref, not `id(layer)`, is the identity test on
    purpose: `id()` of a freed object is recycled by CPython, which is the T-D5
    bug this codebase already paid for once.
    """
    cache = getattr(shared_data, '_mda_layer_shape_validated', None)
    if cache is None:
        return False
    entry = cache.get(layerName)
    if entry is None:
        return False
    generation, layer_ref = entry
    return generation == shared_data._mdaModeParamsGeneration and layer_ref() is layer


def _mark_layer_shape_validated(shared_data, layerName, layer):
    """Record that `layer` matches the current plan, so later frames skip the check."""
    cache = getattr(shared_data, '_mda_layer_shape_validated', None)
    if cache is None:
        cache = {}
        shared_data._mda_layer_shape_validated = cache
    cache[layerName] = (shared_data._mdaModeParamsGeneration, weakref.ref(layer))


def _invalidate_layer_shape_validation(shared_data, layerName):
    """Forget the cached verdict for `layerName` (its layer is being torn down)."""
    cache = getattr(shared_data, '_mda_layer_shape_validated', None)
    if cache is not None:
        cache.pop(layerName, None)


def _get_contrast_refresh_interval(shared_data):
    """Cached `visualisation_config.contrast_refresh_every_n_frames`.

    The raw config value can be a string (it comes back from a QLineEdit), so it
    needs an int() parse + clamp; doing that on every displayed frame is pure
    waste. Cached on shared_data and invalidated by
    `invalidate_contrast_refresh_interval()`, which the Advanced Settings save
    handler calls.
    """
    n = getattr(shared_data, '_contrast_refresh_interval_cache', None)
    if n is None:
        try:
            n = max(1, int(shared_data.config.visualisation_config.contrast_refresh_every_n_frames))
        except (TypeError, ValueError):
            logging.warning('Invalid contrast_refresh_every_n_frames %r; falling back to 10',
                            shared_data.config.visualisation_config.contrast_refresh_every_n_frames)
            n = 10
        shared_data._contrast_refresh_interval_cache = n
    return n


def invalidate_contrast_refresh_interval(shared_data):
    """Drop the cached contrast-refresh interval so the next frame re-reads it."""
    shared_data._contrast_refresh_interval_cache = None


def _maybe_refresh_contrast(shared_data, layer, layerName):
    """Recompute contrast limits every Nth frame instead of every frame.

    bench_live_display measured napari's per-frame auto-contrast recompute
    (`_keep_auto_contrast = True`) as the single largest recurring cost in
    the live-display path (~25-30% of steady-state frame time). Recomputing
    on a throttle keeps the preview's brightness adapting to the data
    without paying the full min/max-scan cost on every frame. N is
    configurable via visualisation_config.contrast_refresh_every_n_frames
    (default 10); set to 1 to recompute every frame (previous behavior).
    """
    counters = _get_contrast_frame_counters(shared_data)
    n = _get_contrast_refresh_interval(shared_data)
    count = counters.get(layerName, 0) + 1
    counters[layerName] = count
    if count % n == 0:
        layer.reset_contrast_limits()


#region real-time visualisation/analysis handling
#These need to be functions outside of any class due to Yield-calling
def _axes_key(axes):
    """Hashable, order-independent form of a frame's `Axes` dict."""
    return tuple(sorted(axes.items()))


def _record_rendered_axes(shared_data, axes):
    """Note that `axes` now exists in the multiDstack store.

    A `set` of `_axes_key` tuples, not the old dict-with-running-integer-key:
    the only consumer is a membership test at finalisation, and the dict form
    made that test O(N_events x M_rendered) dict-subset comparisons. Repeats
    (the same slice displayed twice) collapse instead of accumulating.
    """
    rendered = getattr(shared_data, 'allMDAslicesRendered', None)
    if not isinstance(rendered, set):
        rendered = set()
        shared_data.allMDAslicesRendered = rendered
    rendered.add(_axes_key(axes))


def _rendered_axes_lookup(rendered, key_names):
    """Project every rendered axes tuple onto `key_names`, for O(1) membership.

    The old test was `expected['axes'].items() <= rendered.items()` -- a
    *subset*, because a frame's metadata `Axes` can carry keys the event's
    `axes` does not. Projecting the rendered keys down to exactly the expected
    event's key names preserves that semantics while turning the per-event cost
    into a single set lookup. Built once per distinct expected key set, of
    which a normal MDA has one.
    """
    lookup = set()
    for entry in rendered:
        as_dict = dict(entry)
        try:
            lookup.add(tuple(as_dict[name] for name in key_names))
        except KeyError:
            # This rendered frame does not carry every expected axis, so it can
            # never satisfy the subset test for this key set.
            continue
    return lookup


def _backfill_missing_slices(shared_data, layerName):
    """Fill multiDstack slices the display path never rendered, from NDTiff.

    Only the pycromanager backends need this. Their acquisition callbacks
    (`image_process_fn` / `image_saved_fn`) do no zarr write at all, so the
    fps-throttled display path is the store's only writer and most slices are
    missing -- but they do have an NDTiff `Dataset` to read them back from.
    `MMCORE_PLUS` is the mirror image: T-D3's frame-ring writer already puts
    every frame in the store, and there is no NDTiff dataset to read anyway, so
    the whole pass is skipped rather than run to produce N debug lines.
    """
    dataset = getattr(getattr(shared_data, '_mdaModeAcqData', None), '_dataset', None)
    if dataset is None:
        logging.debug('Backfill skipped: no NDTiff dataset for this acquisition.')
        return 0

    expected_events = shared_data._mdaModeParams or []
    rendered = getattr(shared_data, 'allMDAslicesRendered', None) or set()
    # getDimensionsFromAcqData legitimately returns None for an empty or
    # malformed event list, in which case there is no slice index to write to.
    dimensions = _get_cached_dimensions(shared_data)
    if not expected_events or dimensions is None:
        logging.debug('Backfill skipped: no usable acquisition dimension map.')
        return 0
    dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = dimensions

    # One lookup set per distinct expected key set (normally exactly one),
    # instead of rescanning every rendered frame for every expected event.
    lookups = {}
    filled = 0
    for expectedEntry in expected_events:
        expected_axes = expectedEntry['axes']
        key_names = tuple(sorted(expected_axes))
        lookup = lookups.get(key_names)
        if lookup is None:
            lookup = _rendered_axes_lookup(rendered, key_names)
            lookups[key_names] = lookup
        if tuple(expected_axes[name] for name in key_names) in lookup:
            continue

        try:
            sliceImage = dataset.read_image(
                channel=expected_axes.get('channel'),
                z=expected_axes.get('z'),
                time=expected_axes.get('time'),
                position=expected_axes.get('position'),
                row=expected_axes.get('row'),
                column=expected_axes.get('column'))

            sliceTuple = ()
            for dim_id in range(len(n_entries_in_dims)):
                currentSlice = expected_axes[dimensionOrder[dim_id]]
                currentSliceID = int(np.searchsorted(uniqueEntriesAllDims[dimensionOrder[dim_id]], currentSlice))
                sliceTuple += (int(currentSliceID),)
            shared_data.mdaZarrData[layerName][sliceTuple + (slice(None), slice(None))] = sliceImage
            filled += 1
        except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
            logging.debug('Entry %s tried, but not acquired: %s', expectedEntry, exc)

    logging.debug('Backfill filled %d of %d expected slices from NDTiff.',
                  filled, len(expected_events))
    return filled


def _should_display_now(shared_data, now=None):
    """Rate-limit decision for the live/MDA display path.

    Returns True if a frame arriving *now* would actually be drawn. Called from
    two places:

    * the visualisation worker thread, *before* it marshals a payload across the
      Qt signal boundary -- so frames the GUI would drop anyway never pay the
      cross-thread hand-off cost, and
    * `napariUpdateLive` on the GUI thread, as a second line of defence (cheap,
      and still correct if a frame was queued before the gate closed).

    The decision only reads `shared_data.last_display_update_time`, which is
    stamped at the end of a successful display update, so calling it twice for
    the same frame is idempotent: elapsed time only grows between the two calls.
    """
    if now is None:
        now = time.time()
    #The min_delay_time is here to prevent 2 frames updating 1ms after one another if they arrive like this. Ideally, we wait exactly the frame-time between frames.
    # builtin min() on two scalars -- np.min() here allocated a numpy array per call.
    min_delay_time = min(50/1000, (float(shared_data.MILcore.get_exposure())*0.99)/1000) #Never more than 50 ms! This is on the main thread, so we don't want to unnecessarily wait.
    display_update_time = 1/float(shared_data.config.visualisation_config.fps)#0.05

    elapsed = now - shared_data.last_display_update_time
    if elapsed < display_update_time: #less than a 50-100ms ago already update live mode? wait a bit before displaying live then.
        if logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
            logging.debug('Updated live preview Hindered (due to display update time) at time %s', now)
        return False

    if elapsed < min_delay_time and elapsed > 1/1000:
        if logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
            logging.debug('Updated live preview Delayed (due to display update time) val found %s', elapsed)
            logging.debug('Updated live preview Delayed (due to display update time) by %s', min_delay_time - elapsed)
        # Skip this frame rather than sleeping. napariUpdateLive is called from
        # the main thread (napari dispatches yielded-worker signals there), so
        # sleeping here would freeze the entire UI. Dropping is always safer.
        return False

    return True


def napariUpdateLive(DataStructure):
    """
    Function that finally shows the  image in napari

    Basically the core visualisation method
    """
    if not getattr(shared_data, '_napariUpdateLive_first_call_logged', False):
        logging.info('napariUpdateLive: first yielded call received (layer=%s)', DataStructure.get('layer_name'))
        shared_data._napariUpdateLive_first_call_logged = True

    # Second line of defence: the visualisation worker already applied this same
    # gate before marshalling the payload across the thread boundary, but a frame
    # may still have been in flight when the gate closed.
    if not _should_display_now(shared_data):
        return

    #shared_data.debugImageDisplayTimes.append(time.time())
    napariViewer = DataStructure['napariViewer']
    acqstate = DataStructure['acqState']
    core = DataStructure['core']
    image_queue_analysisA = DataStructure['image_queue_analysis']
    analysisThreads = DataStructure['analysisThreads']
    layerName = DataStructure['layer_name']
    
    
    # Check if the update is in progress
    if shared_data.liveModeUpdateOngoing:
        return
    
    shared_data.liveModeUpdateOngoing = True
    try:
        _napariUpdateLive_locked(DataStructure, napariViewer, acqstate, core, image_queue_analysisA, analysisThreads, layerName)
    except Exception:
        # napariUpdateLive runs as a napari thread_worker 'yielded' slot; an
        # uncaught exception here goes to Qt's default exception hook (stderr),
        # NOT this app's log file, so it's invisible in a windowed GUI session.
        # Log it explicitly so a silently-failing frame update is diagnosable.
        logging.exception('napariUpdateLive: display update failed (frame dropped)')
    finally:
        # Must always release the guard, even on early returns/exceptions above —
        # otherwise a single failed frame permanently freezes the live layer for
        # the rest of the session (every later call bails out at the
        # liveModeUpdateOngoing check above).
        shared_data.liveModeUpdateOngoing = False


def _napariUpdateLive_locked(DataStructure, napariViewer, acqstate, core, image_queue_analysisA, analysisThreads, layerName):
    #Visualise the MDA data on a frame-by-frame method - i.e. not a 'stack', but simply a single image which is replaced every frame update
    if shared_data.config.mda_config.vis_method == 'frameByFrame' or DataStructure['layer_name']=='Live':
        liveImage = DataStructure['data'][0]
        # NOTE: no metadata_refactor here -- the frameByFrame display path never
        # reads the refactored metadata, and on MMCORE_PLUS the acquisition
        # callback has already refactored it once. (multiDstack below does use it.)
        if liveImage is None:
            return
        if acqstate == False:
            return
        # Guarantee C-contiguous memory before handing to napari; avoids a
        # hidden copy inside napari's layer setter when the array is F-order
        # or non-contiguous (e.g. a strided slice from some camera drivers).
        liveImage = np.ascontiguousarray(liveImage)
        liveImageLayer = getLayerIdFromName(layerName,napariViewer,shared_data)

        #If it's the first liveImageLayer
        if not liveImageLayer:
            logging.info('napariUpdateLive: creating "%s" layer, shape=%s dtype=%s', layerName, liveImage.shape, liveImage.dtype)
            nrLayersBefore = len(napariViewer.layers)
            #The following line takes 2 seconds to run: #TODO: optimize
            # rendering='attenuated_mip' is a 3-D volumetric mode; for 2-D
            # live images use the default 2-D renderer (omit the kwarg).
            layer = napariViewer.add_image(liveImage, colormap=DataStructure['layer_color_map'],name = layerName)
            #Set correct scale - in nm
            if shared_data.MILcore.get_pixel_size_um() != 0:
                layer.scale = [shared_data.MILcore.get_pixel_size_um(),shared_data.MILcore.get_pixel_size_um()] #type:ignore
            else:
                logging.error('Pixel size in MM set to 1, probably not set properly in MicroManager, please set this!')
                layer.scale = [1,1]
            # `_keep_auto_contrast = True` recomputes contrast limits (a full
            # min/max scan) on every single frame update below -- bench_live_display
            # measured this as the single largest recurring per-frame cost in the
            # display path (~25-30% of steady-state frame time at 512-2048px).
            # Recompute periodically instead (see contrast_refresh_every_n_frames)
            # so brightness still adapts, just not on every frame.
            layer._keep_auto_contrast = False #type:ignore
            _get_contrast_frame_counters(shared_data)[layerName] = 0
            napariViewer.reset_view()
        #Else if the layer already exists, replace it!
        else:
            # layer is present; update in-place to avoid reallocating the
            # layer's internal data pointer when shape and dtype match.
            layer = napariViewer.layers[liveImageLayer[0]]
            if layer.data.shape == liveImage.shape and layer.data.dtype == liveImage.dtype:
                layer.data[:] = liveImage
                layer.refresh()  # in-place mutation doesn't trigger napari's setter; must refresh manually
                _maybe_refresh_contrast(shared_data, layer, layerName)
            else:
                # Shape/dtype changed (e.g. ROI or binning changed mid-session) --
                # force an immediate contrast recompute rather than waiting for the
                # throttle, since limits fitted to the old shape/range would
                # otherwise look wrong until the next scheduled refresh.
                layer.data = liveImage
                layer.reset_contrast_limits()
                _get_contrast_frame_counters(shared_data)[layerName] = 0
            logging.debug('Put liveImage in the live layer')
            
    #Visualise the MDA data via a 'stack' - i.e. a multiD method where the user can (later) scroll through the frames
    elif shared_data.config.mda_config.vis_method == 'multiDstack':
        # NOTE: layerName is guaranteed != 'Live' anywhere in this branch. The
        # frameByFrame branch above already intercepts every DataStructure with
        # layer_name == 'Live' via its `or DataStructure['layer_name'] == 'Live'`
        # condition, regardless of vis_method - so a 'Live'-named frame always gets
        # routed (and contrast-throttled, see _maybe_refresh_contrast) there first
        # and never reaches this elif. The `layerName == 'Live'` sub-cases below are
        # therefore unreachable under the current dispatch; left in place rather than
        # removed to avoid a speculative behavior change outside this audit's scope.
        if DataStructure['finalisationProcedure'] == False:
            latestImage = DataStructure['data'][0]
            metadata = utils.metadata_refactor(DataStructure['data'][1],shared_data)
            if latestImage is None:
                return
            if acqstate == False:
                return
            # Guarantee C-contiguous memory for zarr writes (same reason as frameByFrame).
            latestImage = np.ascontiguousarray(latestImage)
            liveImageLayer = getLayerIdFromName(layerName,napariViewer,shared_data)
        
            if layerName != 'Live':
                #In case MDA is done repeatedly, the layer already exists, but the dimensions might be wrong. If this is the case, we reshape the MDA layer
                #
                #Validated once per acquisition, not once per frame (T-E3). An
                #existing layer's shape only stops matching when the plan changes
                #or the layer object is replaced, and _layer_shape_already_validated
                #keys on exactly those two things -- so the steady state here is a
                #dict lookup plus a weakref deref, instead of re-deriving the plan's
                #dimensions and walking them with a teardown (layers.pop + zarr
                #reset + full texture re-upload) waiting on any mismatch.
                if liveImageLayer and not _layer_shape_already_validated(
                        shared_data, layerName, napariViewer.layers[liveImageLayer[0]]):
                    dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = _get_cached_dimensions(shared_data)
                    
                    #Assume the dimensions are correct
                    correctDimensions = True
                    
                    #Then check if anywhere the dimensions of the layer are wrong
                    #Check if we have the correct nr of dimensions
                    CurrentLayer = napariViewer.layers[liveImageLayer[0]]
                    if CurrentLayer.ndim != len(uniqueEntriesAllDims)+2: #Note: +2 for image xy
                        correctDimensions = False
                    else:
                        layerData = CurrentLayer.data
                        #Check each dimension as follows:
                        for dim_id in range(0,len(uniqueEntriesAllDims)):
                            #Check if it has the correct label
                            # logging.debug(f'axis_labels: {napariViewer.dims.axis_labels[dim_id]} vs {dimensionOrder[dim_id]}')
                            # if napariViewer.dims.axis_labels[dim_id] != dimensionOrder[dim_id]:
                            #     correctDimensions = False
                            #     break
                            #Check it has the correct length:
                            if logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
                                logging.debug(f'range: {layerData.shape[dim_id]} vs {n_entries_in_dims[dim_id]}')
                            if int(layerData.shape[dim_id]) != n_entries_in_dims[dim_id]:
                                correctDimensions = False
                                break
                            
                    #Remove the layer if the dimensions are wrong
                    if correctDimensions == True:
                        #Matches the current plan: record it so subsequent frames of
                        #this acquisition skip the check entirely.
                        _mark_layer_shape_validated(shared_data, layerName, CurrentLayer)
                    else:
                        #Logged at INFO, not DEBUG: after T-E3 this must happen at most
                        #once per acquisition, so seeing it mid-run is the signal that
                        #something re-derived different dimensions under a live layer.
                        logging.info('Layer %r no longer matches the acquisition plan; '
                                     'rebuilding it (expected %s dims of %s)',
                                     layerName, len(uniqueEntriesAllDims) + 2, n_entries_in_dims)
                        _invalidate_layer_shape_validation(shared_data, layerName)
                        logging.debug('removing mdaZarrData - looping over layers')
                        #Remove the mdaZarrData array and ensure that we create a new layer
                        for tLayerIndex in range(0,len(napariViewer.layers)):
                            tLayer = napariViewer.layers[tLayerIndex]
                            logging.debug(f'layer: {tLayer}, comparing with {napariViewer.layers[liveImageLayer[0]].name}, boolTest {str(tLayer) == str(napariViewer.layers[liveImageLayer[0]].name)}')
                            if str(tLayer) == str(napariViewer.layers[liveImageLayer[0]].name):
                                #If we found the layer, delete it, and ensure we create a new one
                                logging.debug(f'found layer to remove: {tLayer} at {tLayerIndex}')
                                napariViewer.layers.pop(tLayerIndex)
                                shared_data.mdaZarrData[layerName] = None
                                # The layer that referenced this store is gone, so
                                # the store can go with it (T-D7). A fresh one is
                                # created just below.
                                shared_data.release_zarr_temp_dir(layerName)
                                liveImageLayer = False
                                break
        
            #If it's the first layer
            if not liveImageLayer:
                if layerName != 'Live':
                    logging.debug(f'creating layer with name {layerName} via multiDstack method')
                    dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = _get_cached_dimensions(shared_data)
                    logging.debug(f"obtained dimensions: {dimensionOrder} and n_entries_in_dims: {n_entries_in_dims}")
                    
                    shape = n_entries_in_dims
                    # Zarr may have been pre-created by _preinit_mda_zarr before run_mda()
                    # started (MMCORE_PLUS fast acquisitions). Reuse it so frameReady writes
                    # are not lost.
                    if shared_data.mdaZarrData.get(layerName) is None:
                        # One creation site, one explicit dtype (T-D1). The frame
                        # in hand carries the camera's own dtype, so use it rather
                        # than asking the core from the GUI thread.
                        _create_mda_zarr(shared_data, layerName, shape,
                                         latestImage.shape[0], latestImage.shape[1],
                                         latestImage.dtype)
                        #Seed position 0 with the current frame
                        shared_data.mdaZarrData[layerName][(0,) * len(shape) + (slice(None),slice(None))] = latestImage
                    
                    layer = napariViewer.add_image(shared_data.mdaZarrData[layerName], colormap=DataStructure['layer_color_map'],name = layerName)
                    #Set correct scale - in nm
                    if shared_data.MILcore.get_pixel_size_um() != 0:
                        layer.scale = [shared_data.MILcore.get_pixel_size_um(),shared_data.MILcore.get_pixel_size_um()] #type:ignore
                    else:
                        logging.error('Pixel size in MM set to 1, probably not set properly in MicroManager, please set this!')
                        layer.scale = [1,1]
                    # Same throttle the frameByFrame path uses (T-E2). With
                    # `_keep_auto_contrast = True` napari runs reset_contrast_limits()
                    # -- a full min/max scan of the freshly decompressed slice -- on
                    # *every* re-slice, and the multiDstack path re-slices once per
                    # dimension per frame. Recompute every Nth displayed frame instead
                    # (visualisation_config.contrast_refresh_every_n_frames, default 10)
                    # so brightness still adapts.
                    layer._keep_auto_contrast = False #type:ignore
                    # Seeded at -1, not 0 as the frameByFrame path does, so the very
                    # first update frame refreshes and every Nth one after it.
                    # frameByFrame can start at 0 because it calls add_image() with a
                    # real frame, which napari fits contrast to; here add_image() gets
                    # a zarr store that is still all zeros (or holds one seed frame),
                    # so limits fitted at creation are meaningless and waiting N
                    # frames to replace them would show a dark stack at every MDA
                    # start.
                    _get_contrast_frame_counters(shared_data)[layerName] = -1

                    # Built from this plan's dimensions a few lines up, so it
                    # matches by construction -- record that, and the first frame
                    # after creation skips the validation walk too (T-E3).
                    _mark_layer_shape_validated(shared_data, layerName, layer)

                    for dim_id in range(len(n_entries_in_dims)):
                        napariViewer.dims.set_axis_label(dim_id, dimensionOrder[dim_id])
                        logging.info(f"Setting axis label {dim_id} to {dimensionOrder[dim_id]}")
                    napariViewer.reset_view()
                    
                    #set the napariViewer to the correct slices, in one update
                    #(see the per-frame call below for why the sequence form).
                    napariViewer.dims.set_current_step(
                        list(range(len(n_entries_in_dims))),
                        [0] * len(n_entries_in_dims))
                    logging.info("Set all %d current steps to 0", len(n_entries_in_dims))
                else:
                    nrLayersBefore = len(napariViewer.layers)
                    layer = napariViewer.add_image(latestImage, colormap=DataStructure['layer_color_map'],name = layerName)
                    #Set correct scale - in nm
                    if shared_data.MILcore.get_pixel_size_um() != 0:
                        layer.scale = [shared_data.MILcore.get_pixel_size_um(),shared_data.MILcore.get_pixel_size_um()] #type:ignore
                    else:
                        logging.error('Pixel size in MM set to 1, probably not set properly in MicroManager, please set this!')
                        layer.scale = [1,1]
                    layer._keep_auto_contrast = True #type:ignore
                    napariViewer.reset_view()
            #Else if the layer already exists, replace it!
            else:
                if layerName != 'Live':
                    # logging.debug(f'updating layer with name {layerName} via multiDstack method')
                    # One writer per frame (T-D2). The acquisition side writes every
                    # frame -- that is why it exists, the vis queue drops frames --
                    # and stamps the index it used. When that stamp is present this
                    # frame is already in the store, so writing it again is a full
                    # chunk re-encode of identical data, on the GUI thread. Reuse
                    # the index instead; it is also the one actually written.
                    sliceTuple = metadata.get(ZARR_WRITTEN_SLICE_KEY)
                    if sliceTuple is None:
                        # No acquisition-side write for this frame: both pycromanager
                        # paths, and any frame whose ring write failed. The display
                        # path is then the only writer and must do the work.
                        dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = _get_cached_dimensions(shared_data)

                        #Determine in which multi-D slice the image should be added:
                        sliceTuple = ()
                        for dim_id in range(len(n_entries_in_dims)):
                            currentSlice = metadata['Axes'][dimensionOrder[dim_id]]
                            currentSliceID = int(np.searchsorted(uniqueEntriesAllDims[dimensionOrder[dim_id]], currentSlice))
                            if logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
                                logging.debug(f"currentSlice[{dim_id}]: {currentSliceID}")
                            sliceTuple += (int(currentSliceID),)

                        shared_data.mdaZarrData[layerName][sliceTuple + (slice(None),slice(None))] = latestImage

                    #set the napariViewer to the correct slice: reuse the indices
                    #already computed for sliceTuple above rather than re-running
                    #the same searchsorted per dimension a second time.
                    #
                    #One batched call, not one per dimension (T-E1). Each scalar
                    #call assigns napari's `Dims.point` separately, emitting a
                    #`point` event and forcing a complete re-slice -- chunk fetch,
                    #decompress, contrast rescan, GPU upload -- so a 4-D plan cost
                    #four full re-slices per displayed frame. `set_current_step`
                    #also accepts sequences, and that form routes through a single
                    #`set_point`, which builds the whole tuple and assigns `point`
                    #once. Measured against the pinned napari 0.7.0: 4 point events
                    #for the per-axis loop, 1 for the batched call, same resulting
                    #`current_step`.
                    displaySlice = _slice_safe_to_display(shared_data, sliceTuple)
                    napariViewer.dims.set_current_step(list(range(len(displaySlice))),
                                                       list(displaySlice))

                    # Throttled auto-contrast (T-E2), after the sliders have moved so
                    # the limits are fitted to the slice now on screen. Replaces
                    # napari's per-re-slice recompute that `_keep_auto_contrast = True`
                    # used to drive.
                    _maybe_refresh_contrast(shared_data,
                                            napariViewer.layers[liveImageLayer[0]],
                                            layerName)

                    #Store exactly which axes is rendered
                    _record_rendered_axes(shared_data, metadata['Axes'])
                else:
                    # layer is present, replace its data
                    layer = napariViewer.layers[liveImageLayer[0]]
                    #Also move to top
                    napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
                    layer.data = latestImage
                    
        elif DataStructure['finalisationProcedure'] == True:
            #Render the missing images in the MDA acquisition.
            #
            #This used to be an O(N_events x M_rendered) subset scan with a
            #`time.sleep(0.001)` and an NDTiff `read_image()` per missing frame,
            #on the GUI thread -- and because the vis queue is fps-throttled,
            #"missing" is most of the acquisition, so a large MDA froze the UI
            #for seconds at the end of every run. The scan is now a set lookup
            #and the pass is skipped entirely on backends that have no NDTiff
            #dataset to read back from (T-D4).
            shared_data._busy = True
            try:
                _backfill_missing_slices(shared_data, layerName)
            finally:
                shared_data._busy = False

            #napari does not watch a zarr array for writes, so whatever the
            #backfill (or the acquisition-side writer) put in the store only
            #appears once the layer is refreshed and the sliders are pointed at
            #a real slice.
            finalLayer = getLayerIdFromName(layerName, napariViewer, shared_data)
            if finalLayer:
                try:
                    napariViewer.layers[finalLayer[0]].refresh()
                except (AttributeError, IndexError, KeyError) as exc:
                    logging.debug('Final layer refresh skipped: %s', exc)
            logging.debug('Finalised up visualisation...')

    shared_data.last_display_update_time = time.time()

class _AcqTransitionSignals(QObject):
    """Live/MDA transition progress, so the toggle can disable itself (T-F10).

    `started` fires when a transition has to wait for a previous acquisition
    worker to finish tearing down; `finished` carries True if it did stop in
    time, False if `ACQ_STOP_TIMEOUT_S` elapsed. Both are emitted on the GUI
    thread, so a widget slot can act on them directly.
    """

    started = pyqtSignal()
    finished = pyqtSignal(bool)


class napariHandler:
    # Max time to wait, in acqModeChanged, for a previous acquisition worker to
    # fully stop before allowing a new one to start. Generous relative to normal
    # native cancel/drain time (sub-second in practice) without hanging the
    # calling (usually GUI) thread indefinitely if teardown is genuinely stuck.
    ACQ_STOP_TIMEOUT_S = 10.0

    # Frame-ring depth used when the ring only feeds the display + RT-analysis
    # fan-out. Both of those drop frames at their own gate anyway, so a backlog
    # buys nothing and a shallow ring turns a slow consumer into a visible
    # `dropped` count instead of into latency.
    FRAME_RING_CAPACITY_DISPLAY = FRAME_RING_CAPACITY
    # Depth used when the consumer also has to write every frame into the
    # multiDstack zarr store: a dropped frame there is a permanently black slice
    # (the MMCORE_PLUS backend has no NDTiff store to recover it from), so the
    # ring must absorb a disk-write hiccup rather than overwrite.
    FRAME_RING_CAPACITY_STORAGE = 256

    #: How long to wait for pymmcore-plus' output handler to finalise the file it
    #: wrote after the sequence ends. OME-TIFF assembles the whole stack at that
    #: point, so this is proportional to acquisition size, not a quick flush.
    MDA_WRITER_FINALISE_TIMEOUT_S = 300.0
    # How long _stop_frame_ring_consumer waits for the consumer to drain and exit.
    FRAME_RING_DRAIN_TIMEOUT_S = 10.0
    # True only while run_liveSequence_worker is driving the camera. A class
    # attribute (not just an __init__ assignment) so a stray late callback on a
    # half-built or torn-down handler reads False rather than raising.
    _live_sequence_active = False

    # Idle back-off in run_liveSequence_worker when the circular buffer is empty.
    # Short enough to stay well inside one frame interval at any realistic
    # exposure (0.5 ms vs. >=1 ms/frame), so the displayed frame's latency is
    # set by the camera rather than by this loop. Every poll is one
    # @_hardware_locked MIL call, so it cannot be zero: on PYCROMANAGER_JAVA it
    # is a bridge round trip, and the lock is shared with the GUI thread's
    # stage/config calls.
    LIVE_SEQUENCE_POLL_S = 0.0005

    def __init__(self, shared_data,liveOrMda='live') -> None:
        logging.debug('#nH - ititalisation of napariHandler')
        self.shared_data = shared_data
        self.napariViewer = shared_data.napariViewer
        if liveOrMda == 'live':
            self.liveOrMda = 'live'
            self.acqstate = shared_data.liveMode
        elif liveOrMda == 'mda':
            self.liveOrMda = 'mda'
            self.acqstate = shared_data.mdaMode
        # Define a flag to control the continuous task
        self.stop_continuous_task = False
        # empty queue for (live) image data
        self.visualisation_queue = deque(maxlen=10)
        # Create a queue to pass image data between threads
        self.image_queue_analysis = deque(maxlen=10)
        # Create a signal to communicate between threads
        self.mda_acq_done_signal = pyqtSignal(bool)
        #Event when a new image is put in the queue
        self._new_image = Event() #Event when a new image is put in the queue
        # Worker handle – set by startMDA/LiveVisualisation, cleared on stop
        self.visualisation_worker = None
        # Guards the stop -> start transition so two acquisition workers can never
        # drive the same native MMCore/Java engine concurrently (see the
        # access-violation crash this fixes: rapid Live/MDA toggling started a new
        # worker while the old one was still tearing down the same core.mda /
        # Acquisition object). RLock (not Lock): the worker's own cleanup sets
        # shared_data.liveMode/mdaMode = False from inside the worker thread
        # (below), which re-enters acqModeChanged and would deadlock a plain Lock.
        self._acq_transition_lock = RLock()
        self._worker_stopped_event = Event()
        self._worker_stopped_event.set()  # no worker running yet
        # T-F10: the ON path may have to wait up to ACQ_STOP_TIMEOUT_S for the
        # previous worker. That wait must never happen on the GUI thread, so it
        # is handed to a short-lived thread and the transition resumes from a
        # GUI-thread callback. True while such a continuation is pending.
        self._transition_deferred = False
        self.transition_signals = _AcqTransitionSignals()
        self.acquisition_worker = None  # handle to the in-flight worker, mirrors self.visualisation_worker
        # Bounded hand-off between the frameReady callback (which runs
        # synchronously on pymmcore-plus' MDA thread, see
        # grab_image_liveVis_PyMMCore) and _frame_ring_consumer_loop, which does
        # the actual per-frame work. Re-created with a mode-appropriate capacity
        # in _start_frame_ring_consumer; a ring exists from construction so a
        # stray late callback can never hit an AttributeError.
        self.frame_ring = FrameRing(self.FRAME_RING_CAPACITY_DISPLAY)
        self._frame_ring_thread = None
        self._zarr_writer = None
        self._frame_ring_stop = Event()
        # See _effective_vis_method(); set by run_liveSequence_worker.
        self._live_sequence_active = False

        #Sleep time to keep responsiveness
        self.sleep_time = 1/shared_data.config.visualisation_config.fps #in sec
        self.layerName = 'newLayer'

    def mdaacqdonefunction(self):
        logging.debug('#nH - mdaacqdonefunction called in napariHandler')
        self.shared_data.mdaacqdonefunction()
    
    def put_data_in_visualisation_and_analysis_queues(self,visualisation_queue,analysis_entries,image,metadata):
        """Fan a single acquired frame out to the visualisation queue and to
        every active RT-analysis queue.

        `analysis_entries` is the `shared_data.RTAnalysisQueuesThreads` list
        itself (dicts with 'Queue'/'Thread' keys), not a list of queues. The
        previous signature took a freshly-built list of queues and then rescanned
        RTAnalysisQueuesThreads by object identity to recover the thread that
        owns each one -- O(n^2) plus a throwaway list allocation on every frame.

        The `if len(queue) < 1` drop-gate is deliberate: deeper queueing was
        benchmarked and rejected (see docs/bench-live-display.md). A frame is
        dropped for any consumer that has not yet finished the previous one.
        """
        #Queue for visualisation of the data
        if len(visualisation_queue) < 1:
            visualisation_queue.append([image,metadata]) 
            self.new_image() #give the signal that we have a new image ready to be visualised

        # Timed with perf_counter() only when DEBUG is actually enabled -- this
        # runs once per acquired frame (on the frame-ring consumer thread, or on
        # the pycromanager image_process_fn thread), which can be tens of
        # thousands of times per second with hardware-sequenced acquisition; an
        # f-string here would format eagerly on every call regardless of level.
        debug_enabled = logging.getLogger(__name__).isEnabledFor(logging.DEBUG)
        start = time.perf_counter() if debug_enabled else None

        #Queue(s) for RT analysis of the data -- single pass, thread read directly
        #off the same entry rather than looked up by queue identity.
        for entry in analysis_entries:
            queue = entry.get('Queue') if hasattr(entry, 'get') else None
            if queue is None:
                continue
            if len(queue) < 1:
                queue.append([image,metadata])
                thread = entry.get('Thread')
                if thread is not None:
                    thread.new_image()

        if debug_enabled:
            end = time.perf_counter()
            logging.debug("RT analysis fan-out: %.4fms", (end-start)*1000)

    def grab_image_liveVisualisation_and_liveAnalysis(self,image,metadata, event_queue):
        """
        Function that runs on every frame obtained in live mode and puts it in the image queue(s)

        Inputs: array image: image from micromanager
                metadata: metadata from micromanager
        """
        if logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
            logging.debug(f'#nH - Updated live preview requesting grab_image_liveVisualisation_and_liveAnalysis at time {time.time()}')
        if self.acqstate:
            self.put_data_in_visualisation_and_analysis_queues(self.visualisation_queue,self.shared_data.RTAnalysisQueuesThreads,image,metadata)
            #Give image and metadata back for storage done by pycromanager in case of MDA, NOT in case of live-viewing.
            if not self.shared_data.liveMode:
                return image, metadata
        else:
            logging.info('Broke off live mode')
            event_queue.clear()
            try:
                self.shared_data.MILcore.stop_sequence_acquisition()
                logging.debug('aborted acquisition')
            except (RuntimeError, OSError, AttributeError) as exc:
                logging.warning('Stop-sequence on live abort failed: %s', exc)
            return None
    
    def grab_image_liveVis_PyMMCore(self,image: np.ndarray, event: useq.MDAEvent, metadata: dict):
        """frameReady callback — a pure hand-off, nothing else.

        This is connected with Qt.DirectConnection (see
        _connect_mda_signal_direct), so it runs *synchronously on
        pymmcore-plus' own MDA thread*: everything done here happens in front
        of the next camera frame. It therefore only pushes the frame into
        `self.frame_ring` and returns; metadata refactoring, the zarr write and
        the analysis fan-out all happen on the consumer thread
        (_frame_ring_consumer_loop).

        The broad try/except stays: an uncaught exception on a DirectConnection
        callback otherwise vanishes silently — the MDA keeps running and the
        frame count in the log looks normal, but no frame reaches the vis queue.
        """
        if self.acqstate:
            try:
                if not getattr(self, '_first_frame_logged', False):
                    logging.info('grab_image_liveVis_PyMMCore: first frame received, shape=%s dtype=%s', image.shape, image.dtype)
                    self._first_frame_logged = True
                self.frame_ring.push(image, metadata)
            except Exception:
                logging.exception('grab_image_liveVis_PyMMCore: frame hand-off failed (frame dropped)')
        else:
            logging.info('Need to break off!')
            self.shared_data.MILcore.stop_sequence_acquisition()

    def _effective_vis_method(self) -> str:
        """The visualisation method actually in force for the current frame.

        T-C4. `multiDstack` renders by indexing a zarr array with the
        acquisition axes of an MDAEvent. The sequence live path (T-C3) has no
        MDAEvents and no real axes -- its `Axes` is a synthesised
        `{'time': n}` counter -- so that rendering cannot work with it, and
        letting it try would write frames into a store nothing can index back
        out: silent black slices, exactly what T-C4 exists to prevent.

        `frameByFrame` is the honest answer for a preview, and it is also what
        the display already does: `_napariUpdateLive_locked` routes any
        DataStructure named 'Live' to its frameByFrame branch regardless of
        `vis_method`. This makes the storage side agree with the display side
        instead of quietly disagreeing with it.

        The user's configured value is never written back -- this is an
        override for the duration of live mode, not a settings change, so a
        crash mid-live cannot leave `frameByFrame` persisted.
        """
        configured = self.shared_data.config.mda_config.vis_method
        if self._live_sequence_active and configured == 'multiDstack':
            return 'frameByFrame'
        return configured

    def _process_ring_frame(self, image, metadata):
        """Per-frame work, off the acquisition thread.

        Was the body of grab_image_liveVis_PyMMCore until T-A7. Since T-D3 the
        zarr write is only *queued* here -- `ZarrFrameWriter` does it on its own
        thread -- so this stays fast even when the disk does not.
        """
        metadata = utils.metadata_refactor(metadata, self.shared_data)
        # For multiDstack MDA: write every frame directly to zarr so fast acquisitions
        # don't leave black slices (vis queue only passes ~fps frames/s, rest are dropped).
        # _effective_vis_method (not the raw config) so the sequence live path, which
        # has no real acquisition axes to index the store by, never gets here (T-C4).
        if self._effective_vis_method() == 'multiDstack':
            self._try_write_frame_to_zarr(image, metadata)
        self.put_data_in_visualisation_and_analysis_queues(self.visualisation_queue,self.shared_data.RTAnalysisQueuesThreads,image,metadata)

    def _frame_ring_consumer_loop(self):
        """Drain `self.frame_ring` until stopped, then drain what is left.

        Never touches the producer's timing: a slow frame here costs a ring
        drop, not a stalled camera thread.
        """
        native_id = get_native_id()
        self.shared_data.register_perf_thread_label(native_id, 'Frame-ring consumer (frameReady -> vis/RT queues)')
        try:
            while not self._frame_ring_stop.is_set():
                # Short timeout rather than an untimed wait: the stop flag is set
                # by another thread and must be noticed even if no frame follows.
                self.frame_ring.wait(timeout=0.1)
                self._drain_frame_ring()
            # Post-stop drain: frames pushed between the last camera frame and
            # the stop request still have to be written/displayed.
            self._drain_frame_ring()
        finally:
            self.shared_data.unregister_perf_thread_label(native_id)

    def _drain_frame_ring(self):
        while True:
            item = self.frame_ring.pop_next()
            if item is None:
                return
            try:
                self._process_ring_frame(item[0], item[1])
            except Exception:
                logging.exception('Frame-ring consumer: frame processing failed (frame dropped)')

    def _start_frame_ring_consumer(self, needs_every_frame: bool):
        """Start the consumer thread for one acquisition run.

        `needs_every_frame` selects the ring depth: the multiDstack MDA path
        writes each frame into zarr, where a drop is a permanently black slice.
        """
        self._stop_frame_ring_consumer()  # idempotent; also joins a stale thread
        capacity = self.FRAME_RING_CAPACITY_STORAGE if needs_every_frame else self.FRAME_RING_CAPACITY_DISPLAY
        self.frame_ring = FrameRing(capacity)
        self._frame_ring_stop = Event()
        self._frame_ring_thread = Thread(
            target=self._frame_ring_consumer_loop,
            name=f'GladosFrameRing-{self.liveOrMda}',
            daemon=True,
        )
        self._frame_ring_thread.start()
        logging.debug('Frame-ring consumer started (capacity=%d)', capacity)

    def _stop_frame_ring_consumer(self):
        """Stop the consumer, wait for it to drain, and report dropped frames.

        Then stop the storage writer -- strictly in that order, since the
        consumer is what submits to it, and a writer closed first would reject
        the frames still coming out of the ring's post-stop drain.
        """
        thread = self._frame_ring_thread
        self._frame_ring_thread = None
        if thread is not None:
            self._frame_ring_stop.set()
            # Wake it out of frame_ring.wait() immediately instead of waiting out the
            # poll timeout.
            self.frame_ring.event.set()
            thread.join(timeout=self.FRAME_RING_DRAIN_TIMEOUT_S)
            if thread.is_alive():
                logging.warning('Frame-ring consumer did not stop within %.0fs', self.FRAME_RING_DRAIN_TIMEOUT_S)
            dropped = self.frame_ring.dropped
            pushed = self.frame_ring.pushed
            if dropped:
                logging.warning('Frame ring dropped %d of %d frames this acquisition (consumer could not keep up)', dropped, pushed)
            else:
                logging.info('Frame ring handed over %d frames, none dropped', pushed)
        # Unconditional: the writer is started lazily on the first frame, so it
        # can outlive a consumer that was never started or was already stopped.
        self._stop_zarr_writer()

    def _try_write_frame_to_zarr(self, image: np.ndarray, metadata: dict):
        """Write a single frame to the multiDstack zarr array, bypassing the vis queue.

        Called from the frame-ring consumer thread (T-A7 moved it off the frameReady
        callback, which runs on pymmcore-plus' own MDA thread); zarr supports concurrent
        writes to non-overlapping chunks so this is safe alongside the vis worker.
        """
        layerName = self.shared_data.newestLayerName
        if not layerName:
            return
        zarr_data = self.shared_data.mdaZarrData.get(layerName)
        if zarr_data is None:
            return
        try:
            dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = \
                _get_cached_dimensions(self.shared_data)
            sliceTuple = ()
            for dim_name in dimensionOrder:
                current_val = metadata['Axes'][dim_name]
                slice_id = int(np.searchsorted(uniqueEntriesAllDims[dim_name], current_val))
                sliceTuple += (int(slice_id),)
            destination = sliceTuple + (slice(None), slice(None))
            image = np.ascontiguousarray(image)
            # Hand the write to the storage writer thread rather than doing it
            # here (T-D3). A zarr write is disk-bound -- ~9 ms for a 1024x1024
            # uint16 frame, ~4x that on a 2048x2048 sensor -- and this is the
            # frame-ring consumer, which also feeds the display and every RT
            # analysis queue. Charging disk latency to that thread capped the
            # whole frame path at roughly 110 fps and, once the camera outran it,
            # the overwrite-oldest ring silently shed frames that MMCORE_PLUS has
            # no NDTiff store to recover. The writer's own queue absorbs the
            # burst and pushes back instead of dropping.
            writer = self._get_zarr_writer(zarr_data)
            if writer is not None:
                writer.submit(destination, image, tag=sliceTuple)
            else:
                zarr_data[destination] = image
            # Tell the display path this exact frame is in the store already, and
            # at which index (T-D2). The metadata dict travels with the frame
            # through the vis queue and metadata_refactor mutates in place, so the
            # key survives the GUI thread's second call to it. Stamped once the
            # frame is committed to the writer, which retries nothing but does
            # report every failure -- a frame it drops is logged loudly rather
            # than quietly re-written by the GUI thread a full second later.
            metadata[ZARR_WRITTEN_SLICE_KEY] = sliceTuple
        except Exception as exc:
            logging.debug('_try_write_frame_to_zarr skipped: %s', exc)

    def _get_zarr_writer(self, zarr_data):
        """The writer thread for `zarr_data`, started on first use.

        Started lazily rather than alongside the ring consumer because the store
        can be created from either of two places and neither is the consumer's
        start: `_preinit_mda_zarr` builds it before `run_mda()` on the fast-camera
        path, and the display path builds it on the first displayed frame
        otherwise. Keying on the array object means a store re-created mid-session
        (the dimension-mismatch branch does exactly that) retires the old writer
        instead of writing into a discarded array.
        """
        writer = self._zarr_writer
        if writer is not None and writer.array is zarr_data and writer.is_running:
            return writer
        self._stop_zarr_writer()
        try:
            label = getattr(self, 'liveOrMda', 'acq')
            writer = ZarrFrameWriter(zarr_data, name=f'GladosZarrWriter-{label}')
            writer.start()
        except Exception:
            logging.exception('Could not start the zarr writer; writing inline instead')
            return None
        self._zarr_writer = writer
        # Published on shared_data because the display path
        # (`_napariUpdateLive_locked`) is a module-level function with no handler
        # reference, and needs to know how far behind the disk actually is. This
        # is the documented convention for cross-component state.
        self.shared_data.zarrFrameWriter = writer
        return writer

    def _stop_zarr_writer(self):
        """Drain and stop the writer. Idempotent.

        Must run before anything reads the store back (the finalisation pass) and
        before the layer's TemporaryDirectory can be released underneath it.
        """
        writer = self._zarr_writer
        self._zarr_writer = None
        if getattr(self.shared_data, 'zarrFrameWriter', None) is writer:
            self.shared_data.zarrFrameWriter = None
        if writer is None:
            return
        try:
            writer.close()
        except Exception:
            logging.exception('Stopping the zarr writer failed')

    def _preinit_mda_zarr(self, shared_data) -> bool:
        """Pre-create the zarr backing store before run_mda() fires.

        On fast cameras (demo cam) all frameReady callbacks complete before the
        vis worker creates the zarr array, causing _try_write_frame_to_zarr to
        return early (zarr_data is None) for every frame. Creating zarr here,
        while still on the background worker thread, fixes that race.
        """
        layerName = shared_data.newestLayerName
        if not layerName or layerName == 'Live':
            return False
        if shared_data.mdaZarrData.get(layerName) is not None:
            return False
        try:
            dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = \
                _get_cached_dimensions(shared_data)
            h = int(self.shared_data.MILcore.core.getImageHeight())
            w = int(self.shared_data.MILcore.core.getImageWidth())
            dtype = _camera_dtype(self.shared_data)
            _create_mda_zarr(shared_data, layerName, n_entries_in_dims, h, w, dtype)
            return True
        except Exception as exc:
            logging.warning('_preinit_mda_zarr failed: %s', exc)
            return False

    def PyMMCore_finishedAcqCallback(self,sequence: useq.MDASequence):
        logging.info("MDA sequence finished: %s", sequence)
        self.shared_data.tempData = sequence

    def PyMMCore_cancelledAcqCallback(self,sequence: useq.MDASequence):
        logging.info("MDA sequence cancelled: %s", sequence)
        self.shared_data.tempDataC = sequence

    def PyMMCore_startedAcqCallback(self,sequence: useq.MDASequence):
        logging.info("MDA sequence started")
        #Create a new NDTiff stack to store images in - for sure used for internal logic - possibly adding something later for secondary saving?
        #shared_data owns the TemporaryDirectory: constructing one inline and
        #keeping only .name let its finalizer delete the directory immediately,
        #so the makedirs below recreated it with nothing owning its cleanup (T-D7).
        tempdataloc = os.path.join(self.shared_data.new_pyMMC_temp_dir().name,'ndtiff_data')
        
        #if it doesn't exist, create it
        if not os.path.exists(tempdataloc):
            os.makedirs(tempdataloc)
        
        # print('storing temp data in : ', tempdataloc)
        summary_metadata = {'name_1': 123, 'name_2': 'something else'} # make this whatever you want
        from ndstorage import NDTiffDataset
        shared_data.pyMMCdataset = NDTiffDataset(tempdataloc, summary_metadata=summary_metadata, writable=True)
        
        #TODO: summary metadata
        self.shared_data.tempDataStart = sequence
    
    def grab_image_liveVisualisation_and_liveAnalysis_savedFn(self,axes,dataset, event_queue):
        """ 
        Function that runs on every frame obtained in live mode and putis in the image queue
        
        Inputs: array image: image from micromanager
                metadata: metadata from micromanager
        """
        if logging.getLogger(__name__).isEnabledFor(logging.INFO):
            logging.info(f'#nH - Updated preview requesting grab_image_liveVisualisation_and_liveAnalysis_savedFn at time {time.time()}')
        # shared_data.debugImageArrivalTimes.append(time.time())
        if self.acqstate:
            #Check if there is any reason to read the image:
            reasonToReadImage = False
            #Check if it should be put in the visualisation queue
            if len(self.visualisation_queue) < 2:
                reasonToReadImage = True
            #Check if it should be put in any of the analysis queues
            for queue in [item['Queue'] for item in self.shared_data.RTAnalysisQueuesThreads]:
                if len(queue) < 2:
                    reasonToReadImage = True
            if len(self.image_queue_analysis) < 2:
                reasonToReadImage = True
                
            if reasonToReadImage:
                image = dataset.read_image(**axes)
                metadata = {}
                metadata['Axes']=axes
                logging.debug("metadata: %s", metadata)
                self.put_data_in_visualisation_and_analysis_queues(self.visualisation_queue,self.shared_data.RTAnalysisQueuesThreads,image,metadata)
            
        else:
            logging.info('Broke off live mode')
            event_queue.clear()
            try:
                self.shared_data.MILcore.stop_sequence_acquisition()
                logging.debug('aborted acquisition')
            except (RuntimeError, OSError, AttributeError) as exc:
                logging.warning('Stop-sequence on live abort failed: %s', exc)

        # return image, metadata
        
    def _live_sequence_metadata(self, raw, frame_index, constants):
        """Build the per-frame metadata dict for the sequence live path.

        The continuous-sequence path produces no MDAEvent, so there is no
        `mda_event` key and `utils.metadata_refactor` passes the dict straight
        through (it only rewrites `Axes` when an mda_event is present). What
        downstream code actually reads is `Axes`, so that has to be synthesised
        here with a monotonic time counter; `Time`, `Exposure`, `ROI` and
        `PixelSize_um` mirror the shape the MMCORE_PLUS frames carried.

        `constants` is read once per acquisition, not per frame -- Exposure,
        ROI and PixelSize_um are each an @_hardware_locked MIL call.
        """
        metadata = dict(raw) if raw else {}
        metadata.setdefault(
            'Time', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")
        )
        metadata.update(constants)
        metadata['Axes'] = {'time': frame_index}
        return metadata

    def run_liveSequence_worker(self, parent):
        """Live mode as a continuous sequence acquisition (`live_mode_method='sequence'`).

        Blocks until `self.acqstate` goes False, so the caller's `while
        self.acqstate:` loop exits straight afterwards.

        **Why this exists.** The legacy live path is not a live mode at all --
        it is a `live_mode_nr_frames`-long MDA restarted in a loop, so every
        preview frame is driven through an acquisition engine. On MMCORE_PLUS
        that means a pydantic-validated `MDAEvent` per frame (`_iter_exec_output`
        / `exec_sequenced_event` dominate the committed profiles); on
        PYCROMANAGER_JAVA every frame is written into an NDTiff dataset and then
        read back *over the Java bridge*; and on both, the whole acquisition
        object is torn down and rebuilt every `live_mode_nr_frames` frames
        (~17 s at 60 fps with the default 999).

        This path does what MM's own live window, napari-micromanager and any
        plain pycromanager script do instead: start a continuous sequence
        acquisition and read the circular buffer. It is backend-blind because
        it only calls the MIL primitives added in T-C1 -- no engine, no event,
        no store.

        Frames go into the same `frame_ring` the frameReady callback uses
        (T-A7), so everything downstream of the ring is unchanged.
        """
        MILcore = self.shared_data.MILcore
        policy = self.shared_data.config.mda_config.live_pull_policy
        # Anything other than an explicit 'sequential' means 'latest'. Peeking
        # cannot overflow the buffer no matter how far behind the display
        # falls, which is the right default for a preview; 'sequential' is the
        # opt-in for "I need every frame, in order".
        pull_latest = policy != 'sequential'

        # T-C4: must be set before the ring consumer starts, since the very
        # first frame it processes already consults _effective_vis_method().
        self._live_sequence_active = True
        if self.shared_data.config.mda_config.vis_method == 'multiDstack':
            logging.info(
                "Live: visualisation forced to 'frameByFrame' for the duration of live "
                "mode (configured: 'multiDstack'). The sequence live path produces no "
                "acquisition axes to index a multiDstack zarr store by; the configured "
                "setting is unchanged and still applies to MDA."
            )

        self.shared_data.allMDAslicesRendered = set()
        # Referenced by the finally block's log line, so it has to exist before
        # anything inside the try can raise.
        frame_index = 0
        try:
            # Display-only path: the display and RT analysis each drop frames at
            # their own gate, so a deep ring would buy latency, not throughput.
            # Inside the try so that a failure to start the consumer still clears
            # _live_sequence_active -- a stuck override would silently downgrade
            # the next MDA's multiDstack rendering.
            self._start_frame_ring_consumer(needs_every_frame=False)
            # Drop whatever a previous run left behind, so the first displayed
            # frame is not a stale one.
            MILcore.clear_circular_buffer()
            MILcore.start_continuous_sequence_acquisition(0)
            # Read once, not per frame -- see _live_sequence_metadata.
            constants = {
                'Exposure': MILcore.get_exposure(),
                'PixelSize_um': MILcore.get_pixel_size_um(),
                'ROI': MILcore.get_roi(),
            }
            logging.info(
                'Live: continuous sequence acquisition started (pull policy=%s)', policy
            )
            while self.acqstate:
                if MILcore.get_remaining_image_count() > 0:
                    if pull_latest:
                        image, raw = MILcore.get_last_image_and_metadata()
                        # Peeking consumes nothing, so the frames we skipped
                        # would sit there until the buffer overflowed.
                        MILcore.clear_circular_buffer()
                    else:
                        image, raw = MILcore.pop_next_image_and_metadata()
                    self.frame_ring.push(
                        image, self._live_sequence_metadata(raw, frame_index, constants)
                    )
                    frame_index += 1
                else:
                    time.sleep(self.LIVE_SEQUENCE_POLL_S)
        finally:
            # stop first, then drain: the consumer must not be shut down while
            # the camera is still filling the ring.
            try:
                MILcore.stop_sequence_acquisition()
            except Exception:
                logging.exception('Live: stop_sequence_acquisition() failed')
            self._stop_frame_ring_consumer()
            # Only after the consumer has drained: a frame still in flight must
            # see the same visualisation method as every frame before it.
            self._live_sequence_active = False
            try:
                if MILcore.is_sequence_running():
                    logging.warning(
                        'Live: sequence still running after stop_sequence_acquisition(); '
                        'a later start may be refused'
                    )
            except Exception:
                logging.exception('Live: is_sequence_running() check failed')
            logging.info(
                'Live: continuous sequence acquisition stopped after %d frames', frame_index
            )

    @thread_worker
    def run_MILCoreAcquisition_worker(self,parent):
        """ 
        Worker which handles live mode on/off turning etc
        
        """
        from pycromanager.acquisition.acq_eng_py.internal.engine import HardwareControlException
        shared_data.register_perf_thread_label(get_native_id(), 'MDA/acquisition worker')
        visualisation_queue = parent.visualisation_queue
        shared_data.debugImageArrivalTimes=[]
        shared_data.debugImageDisplayTimes=[]
        global acq
        # shared_data = self.shared_data
        logging.debug('#nH - in run_MILCoreAcquisition_worker')
        #The idea of live mode is that we do a very very long acquisition (10k frames), and real-time show the images, and then abort the acquisition when we stop life.
        #The abortion is handled in grab_image_liveVisualisation_and_liveAnalysis
        # Whole body wrapped in try/finally so the event guarding acqModeChanged's
        # stop -> start transition (see napariHandler.__init__) is always set when
        # this worker truly exits, even on an uncaught exception -- otherwise a
        # future start would wait out ACQ_STOP_TIMEOUT_S and be refused forever.
        try:
            if self.liveOrMda == 'live':
                savefolder = None
                savename = None
                while self.acqstate:
                    if self.shared_data.mdaMode:
                        logging.error('LIVE NOT STARTED! MDA IS RUNNING')
                        self.shared_data.liveMode = False
                    elif shared_data.config.mda_config.live_mode_method == 'sequence':
                        # T-C3: drive the camera directly instead of restarting a
                        # 999-frame MDA. Blocks until self.acqstate goes False, so
                        # this while loop then exits on its own. `mda` keeps the
                        # legacy path below completely untouched.
                        self.run_liveSequence_worker(parent)
                    else:
                        #JavaBackendAcquisition is an acquisition on a different thread to not block napari I believe
                        logging.debug('#nH - starting acq')
                        self.shared_data.allMDAslicesRendered = set()
                        #Already move the live layer to top
                        # logging.debug('BMoved layer to top')
                        # moveLayerToTop(self.shared_data.napariViewer,"Live")
                        savefolder = None
                        savename = None
                        #Acquisitions are slightly tricky. If run Headlessly, we take images directly from image_process_fn. However, if we run with a MM instance running, we use the image_saved_fn

                        if self.shared_data.MILcore.MI() == MIL.MicroscopeInstance.MMCORE_PLUS:
                            logging.info('Connected to PymmCore!')


                            #Frame-ring consumer first: the frameReady callback below is a
                            #pure hand-off into the ring, so a consumer has to be draining it
                            #before the first frame can arrive. Live mode is display-only, so
                            #the shallow (drop-oldest) ring is the right one.
                            self._start_frame_ring_consumer(needs_every_frame=False)
                            #Connect the live update to this upcoming MDA
                            connected_callback = _connect_mda_signal_direct(self.shared_data.MILcore.core.mda.events.frameReady, self.grab_image_liveVis_PyMMCore)
                            #Create the MDA plan
                            mda_sequence_useq = useq.MDASequence(
                                time_plan={"interval": 0.0, "loops": shared_data.config.mda_config.live_mode_nr_frames} #type: ignore
                            )
                            #Set proper expected mda. Store the raw useq.MDASequence rather
                            #than eagerly calling to_pycromanager() here: that fully iterates
                            #and pydantic-validates every MDAEvent up front, which run_mda()
                            #below then does again internally to actually drive acquisition --
                            #wasted work in the common case where nothing ever reads
                            #_mdaModeParams this session. Shared_data._mdaModeParams is a
                            #property that converts lazily (and caches) on first read.
                            shared_data._mdaModeParams = mda_sequence_useq

                            #Actually start the MDA
                            self.shared_data.MILcore.core.run_mda(mda_sequence_useq)
                            logging.info("Started MDA sequence")
                            #Give some time to understand that it's running
                            time.sleep(0.1)
                            # Wait for the MDA to finish. processEvents() used to be polled here
                            # (Phase 13.2 removed it for being slow) — it turned out to be load-
                            # bearing: core.mda.events is a Qt-backed signaler in this GUI app
                            # (pymmcore-plus auto-selects Qt over psygnal whenever a QApplication
                            # is running), and this loop runs on a QThreadPool worker thread with
                            # no event loop of its own, so a Qt.AutoConnection frameReady delivery
                            # would just queue forever undelivered without something pumping it.
                            # Fixed properly at the connect() call above via
                            # _connect_mda_signal_direct (Qt.DirectConnection — synchronous
                            # dispatch on the emitting thread, no polling needed).
                            while self.shared_data.MILcore.core.mda.is_running():
                                time.sleep(0.01)

                            #When it's done, disconnect the callback, then let the consumer
                            #drain whatever the ring still holds before it exits.
                            self.shared_data.MILcore.core.mda.events.frameReady.disconnect(connected_callback)
                            self._stop_frame_ring_consumer()
                            logging.info('Finished live!')
                        else: #Pycromanager backend, either JAVA or Python
                            if shared_data.config.mda_config.backend_method == 'saved':
                                with Acquisition(directory=None, name=None, show_display=False, image_saved_fn = self.grab_image_liveVisualisation_and_liveAnalysis_savedFn ) as acq: #type:ignore
                                    self.shared_data._mdaModeAcqData = acq
                                    events = multi_d_acquisition_events(num_time_points=shared_data.config.mda_config.live_mode_nr_frames, time_interval_s=0)
                                    acq.acquire(events)
                            elif shared_data._headless and shared_data.backend == 'Python':
                                try:
                                    logging.debug(f"Starting mda acq at location %s,%s",savefolder,savename)
                                    with Acquisition(directory=None, name=None, show_display=False, image_process_fn = self.grab_image_liveVisualisation_and_liveAnalysis) as acq: #type:ignore
                                        self.shared_data._mdaModeAcqData = acq
                                        events = multi_d_acquisition_events(num_time_points=shared_data.config.mda_config.live_mode_nr_frames, time_interval_s=0)
                                        acq.acquire(events)
                                except HardwareControlException:
                                    #Early quit of the acquisition
                                    logging.info("Acquisition interrupted.")
                                except Exception as e:
                                    logging.error(f"An actual error occurred: {e}")

                            else:
                                with Acquisition(directory=None, name=None, show_display=False, image_saved_fn = self.grab_image_liveVisualisation_and_liveAnalysis_savedFn ) as acq: #type:ignore
                                    self.shared_data._mdaModeAcqData = acq
                                    events = multi_d_acquisition_events(num_time_points=shared_data.config.mda_config.live_mode_nr_frames, time_interval_s=0)
                                    acq.acquire(events)

                        logging.debug('After Acq Live')
                #Now we're after the livestate
                self.shared_data.MILcore.stop_sequence_acquisition()
                self.shared_data.liveMode = False
                #We clean up, removing all LiveAcqShouldBeRemoved folders in /Temp:
                cleanUpTemporaryFiles(shared_data=self.shared_data)
            elif self.liveOrMda == 'mda':
                while self.acqstate:
                    if self.shared_data.liveMode:
                        self.shared_data.liveMode = False
                        time.sleep(0.2)

                    #JavaBackendAcquisition is an acquisition on a different thread to not block napari I believe
                    logging.debug('#nH - starting MDA acq - before JavaBackendAcquisition')
                    savefolder = None#'./temp'
                    savename = None#'MdaAcqShouldBeRemoved'
                    if self.shared_data._mdaModeSaveLoc[0] != '':
                        savefolder = self.shared_data._mdaModeSaveLoc[0]

                        savefolderAdv = utils.nodz_evaluateAdv(savefolder,self.shared_data.nodzInstance)
                        if savefolderAdv != None:
                            savefolder = savefolderAdv
                        logging.debug(savefolder)

                    if self.shared_data._mdaModeSaveLoc[1] != '':
                        savename = self.shared_data._mdaModeSaveLoc[1]
                        savenameAdv = utils.nodz_evaluateAdv(savename,self.shared_data.nodzInstance)
                        if savenameAdv != None:
                            savename = savenameAdv
                        logging.debug(savename)
                    if self.shared_data._mdaModeNapariViewer != None:
                        napariViewer = self.shared_data._mdaModeNapariViewer
                        showdisplay = True
                    else:
                        napariViewer = None
                        showdisplay = False

                    napariViewer = None
                    showdisplay = False
                    self.shared_data.allMDAslicesRendered = set()
                    #Already move the layer to top
                    # if self.shared_data.newestLayerName != '':
                    #     moveLayerToTop(self.shared_data.napariViewer,self.shared_data.newestLayerName)

                    logging.debug(f"MDABackendMethod is",shared_data.config.mda_config.backend_method)
                    if self.shared_data.MILcore.MI() == MIL.MicroscopeInstance.MMCORE_PLUS:
                        logging.info('Connected to PymmCore!')
                        acq=None
                        #This backend has no NDTiff engine, so pymmcore-plus does the
                        #recording itself via run_mda(output=...) -- see
                        #mmcore_output_path(). Before that, savefolder/savename were
                        #computed here and never read, and the only copy of the data
                        #was the scratch zarr in a TemporaryDirectory that
                        #release_all_temp_dirs() deletes on exit: the MDA saved
                        #nothing at all. The zarr store remains, but as what it always
                        #really was -- the display buffer, not the archive.
                        output_path = mmcore_output_path(shared_data, savefolder, savename)
                        self.shared_data.mdaSavedPath = str(output_path) if output_path else None
                        if output_path is None:
                            logging.warning('pymmcore-plus MDA will not be saved '
                                            '(no Storage folder set, or save format is "none")')
                        else:
                            logging.info('pymmcore-plus MDA will be saved to %s', output_path)

                        #Frame-ring consumer first — see the live-mode branch above. On the
                        #multiDstack path the consumer also writes every frame into zarr, where
                        #a dropped frame is a permanently black slice, so it gets the deep ring.
                        self._start_frame_ring_consumer(
                            needs_every_frame=self.shared_data.config.mda_config.vis_method == 'multiDstack')
                        #Connect the live update to this upcoming MDA
                        connected_callback = _connect_mda_signal_direct(self.shared_data.MILcore.core.mda.events.frameReady, self.grab_image_liveVis_PyMMCore)
                        connected_callback_finishedAcq = _connect_mda_signal_direct(self.shared_data.MILcore.core.mda.events.sequenceFinished, self.PyMMCore_finishedAcqCallback)
                        connected_callback_cancelledAcq = _connect_mda_signal_direct(self.shared_data.MILcore.core.mda.events.sequenceCanceled, self.PyMMCore_cancelledAcqCallback)
                        connected_callback_startedAcq = _connect_mda_signal_direct(self.shared_data.MILcore.core.mda.events.sequenceStarted, self.PyMMCore_startedAcqCallback)
                        # Pre-create zarr so frameReady callbacks can write immediately.
                        # Without this, on fast cameras all frames arrive before the vis
                        # worker creates the zarr, leaving every slice as zeros (black).
                        if self.shared_data.config.mda_config.vis_method == 'multiDstack':
                            self._preinit_mda_zarr(shared_data)
                        #Get the MDA plan
                        mda_sequence_useq = shared_data._mdaModeParams_useq
                        #Actually start the MDA. `output` is what makes pymmcore-plus
                        #write the data; None keeps the old acquire-without-saving
                        #behaviour.
                        mda_thread = self.shared_data.MILcore.core.run_mda(
                            mda_sequence_useq,
                            output=str(output_path) if output_path else None)
                        logging.info("Started MDA sequence")
                        #Give some time to understand that it's running
                        time.sleep(0.1)
                        # See the matching comment in the live-mode wait loop above: frameReady
                        # delivery is now fixed via Qt.DirectConnection at connect() time, so no
                        # processEvents() polling is needed here either.
                        while self.shared_data.MILcore.core.mda.is_running():
                            time.sleep(0.01)
                        #Join the runner thread as well: is_running() can go False
                        #before the output handler has finalised the file it wrote
                        #(OME-TIFF in particular assembles on sequenceFinished), and
                        #the storage path is reported to nodz right after this.
                        if mda_thread is not None:
                            mda_thread.join(timeout=self.MDA_WRITER_FINALISE_TIMEOUT_S)
                            if mda_thread.is_alive():
                                logging.warning('MDA output handler did not finalise within %.0fs',
                                                self.MDA_WRITER_FINALISE_TIMEOUT_S)

                        #When it's done, disconnect the callback, then let the consumer drain
                        #the ring — the multiDstack finalisation pass below must not run while
                        #frames are still pending a zarr write.
                        self.shared_data.MILcore.core.mda.events.frameReady.disconnect(connected_callback)
                        self._stop_frame_ring_consumer()
                        self.shared_data.MILcore.core.mda.events.sequenceStarted.disconnect(connected_callback_startedAcq)
                        # self.shared_data.MILcore.core.mda.events.sequenceFinished.disconnect(connected_callback_finishedAcq)
                        # self.shared_data.MILcore.core.mda.events.sequenceCanceled.disconnect(connected_callback_cancelledAcq)
                        logging.info("Finished MDA!")
                    else: #Pycromanager backend, either JAVA or Python
                        if shared_data.config.mda_config.backend_method == 'saved':
                            logging.debug(f"Starting mda acq at location %s,%s",savefolder,savename)
                            with Acquisition(directory=savefolder, name=savename, show_display=showdisplay,napari_viewer=napariViewer, image_saved_fn = self.grab_image_liveVisualisation_and_liveAnalysis_savedFn ) as acq: #type:ignore
                                self.shared_data._mdaModeAcqData = acq
                                events = self.shared_data._mdaModeParams
                                acq.acquire(events)
                        elif shared_data._headless and shared_data.backend == 'Python':
                            logging.debug(f"Starting mda acq at location %s,%s",savefolder,savename)
                            with Acquisition(directory=savefolder, name=savename,image_process_fn = self.grab_image_liveVisualisation_and_liveAnalysis, show_display=showdisplay, napari_viewer=napariViewer) as acq: #type:ignore
                                self.shared_data._mdaModeAcqData = acq
                                events = self.shared_data._mdaModeParams
                                acq.acquire(events)
                        else:
                            logging.debug(f"Starting mda acq at location %s,%s",savefolder,savename)
                            with Acquisition(directory=savefolder, name=savename, show_display=showdisplay, napari_viewer=napariViewer,image_saved_fn = self.grab_image_liveVisualisation_and_liveAnalysis_savedFn) as acq: #type:ignore
                                self.shared_data._mdaModeAcqData = acq
                                events = self.shared_data._mdaModeParams
                                acq.acquire(events)

                    self.shared_data.mdaMode = False
                    self.acqstate = False #End the MDA acq state

                    if acq is not None:
                        self.shared_data.appendNewMDAdataset(acq.get_dataset())
                    else:
                        # pymmcore-plus backend: pyMMCdataset may be uninitialized or
                        # have received no images (put_image is not yet implemented).
                        try:
                            self.shared_data.pyMMCdataset.finish()
                        except Exception as exc:
                            logging.debug('pyMMCdataset.finish() skipped (pymmcore-plus backend, no images stored yet): %s', exc)

                logging.debug('#nH - Stopping the acquisition from napariHandler')
                #Now we're after the acquisition
                self.shared_data.MILcore.stop_sequence_acquisition()
                self.shared_data.mdaMode = False

                #Signal to all parents that the MDA acquisition is done - in the Nodz MDA, now we would trigger the MDA-based analysis for scoring or so
                parent.mdaacqdonefunction()

                #We clean up, removing all LiveAcqShouldBeRemoved folders in /Temp:
                cleanUpTemporaryFiles(shared_data=self.shared_data)
        finally:
            # Safety net: if run_mda() or an Acquisition raised, the in-branch
            # _stop_frame_ring_consumer() never ran and the consumer thread would
            # outlive the acquisition. Idempotent when it already stopped.
            self._stop_frame_ring_consumer()
            self._worker_stopped_event.set()


    def new_image(self):
        self._new_image.set()

    @thread_worker(connect={'yielded': napariUpdateLive})
    def run_napariVisualisation_worker(self,parent,layerName='Layer',layerColorMap='gray'):
        """
        Worker which handles the visualisation of the live mode queue
        Connected to display_napari function to update display 
        """
        
        # Get a reference to the worker object itself to check for .quit() signals
        current_worker = getattr(self, 'visualisation_worker', None) # Get reference to itself
        self.shared_data.register_perf_thread_label(get_native_id(), 'Visualisation worker (frame queue -> napariUpdateLive)')

        visualisation_queue = parent.visualisation_queue
        # Six of the eight payload keys are constant for the whole run; build them
        # once and shallow-copy per yield instead of re-deriving them per frame.
        # (A fresh dict per yield is required -- the payload crosses a queued Qt
        # signal boundary and the receiver may lag behind the producer.)
        base_payload = {
            'napariViewer': self.shared_data.napariViewer,
            'core': self.shared_data.core,
            'image_queue_analysis': [],#self.image_queue_analysis#-doesn't seem to be required?
            'analysisThreads': [],#self.shared_data.analysisThreads #-doesn't seem to be required?
            'layer_name': layerName,
            'layer_color_map': layerColorMap,
            'finalisationProcedure': False,
        }
        try:
            while self.acqstate:
                # 1. Check if the user called .quit() from the outside
                if current_worker and current_worker.abort_requested:
                    break
                
                # get elements from queue while there is more than one element
                # self._new_image.wait(timeout=0.1)  # old: woke up 10x/s spuriously
                self._new_image.wait(timeout=1.0)  # 1s deadman; acqModeChanged sets this on stop
                self._new_image.clear()
                
                if visualisation_queue:
                    frame = visualisation_queue.popleft()
                    # Apply the display rate-limit here, on the worker thread,
                    # rather than paying the cross-thread signal marshalling for a
                    # frame napariUpdateLive would immediately drop at the very
                    # same gate.
                    if not _should_display_now(self.shared_data):
                        continue
                    DataStructure = dict(base_payload)
                    DataStructure['data'] = frame
                    DataStructure['acqState'] = self.acqstate
                    logging.debug('live mode worker - yield DataStructure')
                    yield DataStructure
        finally:
            # This 'finally' block acts as your "destroy" logic
            # It runs whether the loop finishes naturally or is aborted
            logging.info("Visualization worker: Performing final cleanup")
            visualisation_queue.clear()
            
        # read out last remaining element(s) after end of acquisition
        while visualisation_queue:
            DataStructure = {}
            DataStructure['data'] = visualisation_queue.popleft()
            DataStructure['napariViewer'] = self.shared_data.napariViewer
            DataStructure['acqState'] = self.acqstate
            DataStructure['core'] = self.shared_data.core
            DataStructure['image_queue_analysis'] = self.image_queue_analysis
            DataStructure['analysisThreads'] = [item['Thread'] for item in self.shared_data.RTAnalysisQueuesThreads]
            logging.info('adding analysisThread in run_napariVisualisation_worker 2')
            DataStructure['layer_name'] = layerName
            DataStructure['layer_color_map'] = layerColorMap
            DataStructure['finalisationProcedure'] = False
            yield DataStructure#visualisation_queue.get(block = False)
            
        #Do the final N images
        if self.shared_data.config.mda_config.backend_method == 'multiDstack':
            if layerName == 'MDA':
                logging.debug('Finalising MDA visualisation...')
                DataStructure = {}
                DataStructure['data'] = None
                DataStructure['napariViewer'] = self.shared_data.napariViewer
                DataStructure['acqState'] = self.acqstate
                DataStructure['core'] = self.shared_data.core
                DataStructure['image_queue_analysis'] = self.image_queue_analysis
                DataStructure['analysisThreads'] = [item['Thread'] for item in self.shared_data.RTAnalysisQueuesThreads]
                logging.info('adding analysisThread in run_napariVisualisation_worker 3')
                DataStructure['layer_name'] = layerName
                DataStructure['layer_color_map'] = layerColorMap
                DataStructure['finalisationProcedure'] = True
                napariUpdateLive(DataStructure)
        
        logging.debug("#nH - acquisition done")
        self.shared_data.liveModeUpdateOngoing = False

    def _defer_transition_until_worker_stops(self):
        """Move the wait-for-previous-worker off the GUI thread (T-F10).

        Returns True when the transition has been handed to a background waiter
        and the caller should return immediately; False when the caller should
        do the (blocking) wait itself, which is correct on a worker thread.

        The continuation re-enters `acqModeChanged`, so it re-reads the current
        mode: a user who toggles back off while the previous worker is still
        stopping gets the OFF path, not a stale start.
        """
        from PyQt5.QtWidgets import QApplication

        from glados_pycromanager.GUI.napari_bridge import NapariBridge, get_bridge

        if QApplication.instance() is None:
            # Headless: there is no GUI thread to protect and no event loop to
            # resume from. Block, exactly as before.
            return False
        if not NapariBridge.on_gui_thread():
            # A worker's own thread may block; that is what it is for.
            return False
        if self._transition_deferred:
            # A continuation is already pending and will re-read the mode.
            return True

        bridge = get_bridge(self.shared_data)
        if bridge is None:
            return False

        self._transition_deferred = True
        self.transition_signals.started.emit()

        mode_attribute = 'liveMode' if self.liveOrMda == 'live' else 'mdaMode'

        def _resume_on_gui_thread(_viewer):
            self._transition_deferred = False
            self.transition_signals.finished.emit(stopped_in_time[0])
            if stopped_in_time[0]:
                self.acqModeChanged()
            else:
                logging.error(
                    "Previous %s acquisition worker did not stop within %.0fs of "
                    "being cancelled; refusing to start a new one to avoid a native "
                    "MMCore/Java-bridge race. Try again once the previous acquisition "
                    "has finished.", self.liveOrMda, self.ACQ_STOP_TIMEOUT_S)
                setattr(self.shared_data, mode_attribute, False)

        stopped_in_time = [False]

        def _wait_off_the_gui_thread():
            stopped_in_time[0] = self._worker_stopped_event.wait(
                timeout=self.ACQ_STOP_TIMEOUT_S)
            bridge.submit(_resume_on_gui_thread, wait=False)

        Thread(target=_wait_off_the_gui_thread,
               name='acq-transition-wait', daemon=True).start()
        return True

    def _napari_bridge(self):
        """The GUI-thread receiver for this handler's napari mutations (T-F9)."""
        from glados_pycromanager.GUI.napari_bridge import get_bridge

        return get_bridge(self.shared_data)

    def acqModeChanged(self, newSharedData = None):
        """
        General function which is called if live mode is changed or not. Generally called from sharedFunction - when self._liveMode is altered
        
        Is called, and shared_data.liveMode should be changed seperately from running this funciton
        """
        # logging.debug('#nH - acqModeChanged called from napariHandler')
        # Serializes the whole stop -> start transition per napariHandler instance
        # (RLock: the worker's own cleanup re-enters this method from its own
        # thread via shared_data.liveMode/mdaMode = False, see run_MILCoreAcquisition_worker).
        with self._acq_transition_lock:
            if newSharedData is not None:
                global napariViewer, shared_data, Core
                self.shared_data = newSharedData
                shared_data = self.shared_data
                napariViewer = self.shared_data.napariViewer
                core = self.shared_data.core

            if self.liveOrMda == 'live':
                #Hook the live mode into the scripts here
                if self.shared_data.liveMode == False:
                    #Stop the ongoing acquisition
                    self.shared_data.MILcore.stop_sequence_acquisition()
                    #Signal that there is no acquisition ongoing
                    self.acqstate = False
                    self._new_image.set()  # unblock visualization worker immediately
                    self.stop_continuous_task = True
                    #Clear the image queue
                    self.visualisation_queue.clear()

                    #Check for all RT-analysis and ensure that they are stopping
                    for rtAnalysisThread in [item['Thread'] for item in self.shared_data.RTAnalysisQueuesThreads]:
                        rtAnalysisThread.set_activity(False)

                    #Stop live mode napari display worker
                    napariGlados.stopLiveModeVisualisation(shared_data)

                    logging.info("Live mode stopped")
                else:
                    # Don't start a new acquisition worker until the previous one has
                    # fully torn down -- otherwise two workers can drive the same
                    # native MMCore/Java engine concurrently (the access-violation
                    # crash this guard fixes). See ACQ_STOP_TIMEOUT_S.
                    # T-F10: never do that waiting on the GUI thread -- a single
                    # button click could freeze the UI for the full timeout.
                    if not self._worker_stopped_event.is_set():
                        if self._defer_transition_until_worker_stops():
                            return
                    if not self._worker_stopped_event.wait(timeout=self.ACQ_STOP_TIMEOUT_S):
                        logging.error(
                            "Previous live acquisition worker did not stop within %.0fs of "
                            "being cancelled; refusing to start a new one to avoid a native "
                            "MMCore/Java-bridge race. Try again once the previous acquisition "
                            "has finished.", self.ACQ_STOP_TIMEOUT_S)
                        self.shared_data.liveMode = False
                        return
                    self._worker_stopped_event.clear()

                    self.acqstate = True
                    self.stop_continuous_task = False
                    self._first_frame_logged = False
                    self.shared_data._napariUpdateLive_first_call_logged = False
                    #Always start live-mode visualisation:
                    napariGlados.startLiveModeVisualisation(self.shared_data)
                    #Move layer to top - if it isn't created yet, it will fail
                    # T-F9: acqModeChanged runs on the acquisition worker's own
                    # thread, so this goes through the GUI-thread bridge.
                    self._napari_bridge().move_to_top("Live")

                    #Start the worker to run the pycromanager acquisition
                    worker1 = self.run_MILCoreAcquisition_worker(self) #type:ignore
                    self.acquisition_worker = worker1
                    worker1.start() #type:ignore
                    # worker2 = self.run_analysis_worker(self) #type:ignore

                    #Check for all RT-analysis and ensure that they are starting
                    for rtAnalysisThread in [item['Thread'] for item in self.shared_data.RTAnalysisQueuesThreads]:
                        rtAnalysisThread.set_activity(True)

                    logging.info("Live mode started")
            elif self.liveOrMda == 'mda':
                #Hook the live mode into the scripts here
                if self.shared_data.mdaMode == False:
                    self.acqstate = False
                    self._new_image.set()  # unblock visualization worker immediately
                    self.stop_continuous_task = True
                    #Clear the image queue
                    self.visualisation_queue.clear()


                    #Check for all RT-analysis and ensure that they are stopping
                    for rtAnalysisThread in [item['Thread'] for item in self.shared_data.RTAnalysisQueuesThreads]:
                        rtAnalysisThread.set_activity(False)

                    #Stop live mode napari display worker
                    napariGlados.stopMDAVisualisation(shared_data)

                    logging.info("MDA mode stopped from acqModeChanged")
                    # self.mdaacqdonefunction()
                else:
                    # See the matching guard in the 'live' branch above.
                    # T-F10: never do that waiting on the GUI thread -- a single
                    # button click could freeze the UI for the full timeout.
                    if not self._worker_stopped_event.is_set():
                        if self._defer_transition_until_worker_stops():
                            return
                    if not self._worker_stopped_event.wait(timeout=self.ACQ_STOP_TIMEOUT_S):
                        logging.error(
                            "Previous MDA acquisition worker did not stop within %.0fs of "
                            "being cancelled; refusing to start a new one to avoid a native "
                            "MMCore/Java-bridge race. Try again once the previous acquisition "
                            "has finished.", self.ACQ_STOP_TIMEOUT_S)
                        self.shared_data.mdaMode = False
                        return
                    self._worker_stopped_event.clear()

                    logging.info('mdaMode changed to TRUE')
                    self.acqstate = True
                    self.stop_continuous_task = False
                    #Move layer to top - if it isn't created yet, it will fail
                    if self.shared_data.newestLayerName != '':
                        # T-F9: see the live branch above.
                        self._napari_bridge().move_to_top(self.shared_data.newestLayerName)
                    #Start the two workers, one to run it, one to visualise it.


                    worker1 = self.run_MILCoreAcquisition_worker(self) #type:ignore
                    self.acquisition_worker = worker1
                    # worker2 = self.run_napariVisualisation_worker(self) #type:ignore
                    worker1.start() #type:ignore

                    #Check for all RT-analysis and ensure that they are starting
                    for rtAnalysisThread in [item['Thread'] for item in self.shared_data.RTAnalysisQueuesThreads]:
                        rtAnalysisThread.set_activity(True)

                    # worker2.start()
                    logging.debug("MDA mode started from acqModeChanged")

class napariHandler_liveMode(napariHandler):
    def __init__(self, shared_data) -> None:
        super().__init__(shared_data, liveOrMda='live')

class napariHandler_mdaMode(napariHandler):
    def __init__(self, shared_data) -> None:
        super().__init__(shared_data, liveOrMda='mda')
#endregion

#region NapariWidgets
class dockWidgets(QMainWindow):
    sizeChanged = pyqtSignal(QSize)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sizeChanged.emit(event.size())
        
    def __init__(self):
        logging.debug('dockwidget started')
        super().__init__()
        #Create all the widgets/layouts:
        self.central_widget = QWidget(self)
        self.central_layout = QVBoxLayout()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.layout = QGridLayout() #type:ignore
        
        #Order them logically:
        self.content_widget.setLayout(self.layout)
        self.scroll_area.setWidget(self.content_widget)
        self.central_layout.addWidget(self.scroll_area)
        self.central_widget.setLayout(self.central_layout)
        self.setCentralWidget(self.central_widget)
        
        self.dockWidget = None

        #we end up with self.layout() that's changed by every indiv dockwidget
        
    def getDockWidget(self):
        return self.dockWidget

class dockWidget_MMcontrol(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_MMcontrol started")
        super().__init__()
        #Add the full micro manager controls UI
        self.dockWidget = microManagerControlsUI(self.layout,shared_data)

class dockWidget_MDA(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_MDA started")
        super().__init__()
        
        #load from appdata
        appdata_folder = appdirs.user_data_dir()#os.getenv('APPDATA')
        if appdata_folder is None:
            raise OSError("APPDATA environment variable not found")
        app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
        os.makedirs(app_specific_folder, exist_ok=True)
        if os.path.exists(os.path.join(app_specific_folder, 'glados_state.json')):
            #Load the mda state
            with open(os.path.join(app_specific_folder, 'glados_state.json')) as file:
                gladosInfo = json.load(file)
                mdaInfo = gladosInfo['MDA']
            
            try:
                #Add the full micro manager controls UI
                self.dockWidget = MDAGlados(shared_data.MILcore,MM_JSON,self.layout,shared_data,
                            hasGUI=True,
                            num_time_points = mdaInfo['num_time_points'], 
                            time_interval_s = mdaInfo['time_interval_s'], 
                            time_interval_s_or_ms = mdaInfo['time_interval_s_or_ms'],
                            z_start = mdaInfo['z_start'],
                            z_end = mdaInfo['z_end'],
                            z_step = mdaInfo['z_step'],
                            z_stage_sel = mdaInfo['z_stage_sel'],
                            z_nr_steps = mdaInfo['z_nr_steps'],
                            z_step_distance = mdaInfo['z_step_distance'],
                            z_nrsteps_radio_sel = mdaInfo['z_nrsteps_radio_sel'],
                            z_stepdistance_radio_sel = mdaInfo['z_stepdistance_radio_sel'],
                            channel_group = mdaInfo['channel_group'],
                            channels = mdaInfo['channels'],
                            channel_exposures_ms = mdaInfo['channel_exposures_ms'],
                            xy_positions = mdaInfo['xy_positions'],
                            xyz_positions = mdaInfo['xyz_positions'],
                            position_labels = mdaInfo['position_labels'],
                            exposure_ms = mdaInfo['exposure_ms'],
                            exposure_s_or_ms = mdaInfo['exposure_s_or_ms'],
                            storage_folder = mdaInfo['storage_folder'],
                            storage_file_name = mdaInfo['storage_file_name'],
                            order = mdaInfo['order'],
                            GUI_show_exposure = mdaInfo['GUI_show_exposure'], 
                            GUI_show_xy = mdaInfo['GUI_show_xy'], 
                            GUI_show_z = mdaInfo['GUI_show_z'], 
                            GUI_show_channel = mdaInfo['GUI_show_channel'], 
                            GUI_show_time = mdaInfo['GUI_show_time'], 
                            GUI_show_order = mdaInfo['GUI_show_order'], 
                            GUI_show_storage = mdaInfo['GUI_show_storage'], 
                            GUI_xy_pos_fullInfo = mdaInfo['xy_positions_saveInfo'],
                            GUI_acquire_button = True,
                            autoSaveLoad=True).getGui()
            except KeyError:
                #Add the full micro manager controls UI
                self.dockWidget = MDAGlados(shared_data.MILcore,MM_JSON,self.layout,shared_data,
                            hasGUI=True,
                            GUI_acquire_button = True,
                            autoSaveLoad=True).getGui()
        else: #If no MDA state is yet saved, open a new MDAGlados from scratch
            #Add the full micro manager controls UI
            self.dockWidget = MDAGlados(shared_data.MILcore,MM_JSON,self.layout,shared_data,
                        hasGUI=True,
                        GUI_acquire_button = True,
                        autoSaveLoad=True).getGui()
            
        self.sizeChanged.connect(self.dockWidget.handleSizeChange)

class dockWidget_flowChart(dockWidgets):
    def __init__(self):
        logging.debug("dockWidget_flowchart started")
        super().__init__()
        from glados_pycromanager.GUI.FlowChart_dockWidgets import flowChart_dockWidgets
        self.dockWidget = flowChart_dockWidgets(shared_data.MILcore,MM_JSON,self.layout,shared_data)

class dockWidget_PerformanceMode(dockWidgets):
    def __init__(self):
        logging.debug("dockWidget_PerformanceMode started")
        super().__init__()
        from glados_pycromanager.GUI.performance_mode_widget import PerformanceModeWidget
        self.dockWidget = PerformanceModeWidget(shared_data)
        self.layout.addWidget(self.dockWidget, 0, 0) #type:ignore

class dockWidget_fullGladosUI(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_fullGladosUI started")
        super().__init__()
        # #new QWidget:
        tempWidget = QMainWindow()
        
        ui = Ui_CustomDockWidget()
        ui.setupUi(tempWidget)
        #Open JSON file with MM settings
        MM_JSON_path = os.path.join(sys.path[0], 'MM_PycroManager_JSON.json')
        # with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
        with open(MM_JSON_path) as f:
            MM_JSON = json.load(f)
            
        from glados_pycromanager.GUI.LaserControlScripts import runlaserControllerUI
        form, self.criticalErrors = runlaserControllerUI(shared_data.MILcore,MM_JSON,ui,shared_data)
        #Run the laserController UI        
        #
        #Create a Vertical+horizontal layout:
        self.dockwidgetLayout = QGridLayout()
        #Create a layout for the configs:
        self.analysisLayout = QGridLayout()
        #Add this to the mainLayout:
        self.dockwidgetLayout.addLayout(self.analysisLayout,0,0)
        
        self.analysisLayout.addWidget(ui.centralwidget.children()[1].children()[0],1,1)
        
        self.dockWidget = self.layout.addLayout(self.dockwidgetLayout,0,0)

#endregion

#region HelpfullFunctions
def startLiveModeVisualisation(shared_data,layerName='Live'):
    #Check for running liveVisualisation threads and remove those
    for thread in [item['Thread'] for item in shared_data.RTAnalysisQueuesThreads]:
        if thread.analysisInfo == 'LiveModeVisualisation':
            #Find the thread/queue:
            for item in shared_data.RTAnalysisQueuesThreads:
                if item['Thread'] == thread:
                    #Remove the thread
                    if item['Thread']:
                        # Signal the thread to stop (using an event, for example)
                        item['Thread'].destroy()
                    #Remove the queue
                    if item['Queue']:
                        # Clear the queue
                        while item['Queue']:
                            try:
                                item['Queue'].popleft()
                            except IndexError: # For deque
                                break
                    #remove from shared_data entry
                    shared_data.RTAnalysisQueuesThreads.remove(item)
                    logging.debug('removed old LiveModeVisualisation thread')   
                    break
    
    shared_data.newestLayerName = layerName
    #2024-10-16 refactor attempt: next line isn't needed --> maybe image_queue_analysis isn't needed?
    # create_analysis_thread(shared_data,analysisInfo='LiveModeVisualisation',createNewThread=False,throughputThread=shared_data._livemodeNapariHandler.image_queue_analysis) #type: ignore
    #Start a worker dedicated to running the live mode visualisation
    shared_data._livemodeNapariHandler.visualisation_worker = shared_data._livemodeNapariHandler.run_napariVisualisation_worker(shared_data._livemodeNapariHandler,layerName = layerName)
    shared_data._livemodeNapariHandler.visualisation_worker.finished.connect(_on_worker_fully_stopped_live)

def _on_worker_fully_stopped_live():
    logging.debug("LIVE worker is confirmed DEAD.")
    shared_data._livemodeNapariHandler.visualisation_worker = None

def stopLiveModeVisualisation(shared_data,layerName='Live'):
    if shared_data._livemodeNapariHandler.visualisation_worker is not None:
        shared_data._livemodeNapariHandler.visualisation_worker.yielded.disconnect()
        shared_data._livemodeNapariHandler.visualisation_worker.quit()
        shared_data._livemodeNapariHandler._new_image.set()

def startMDAVisualisation(shared_data,layerName='MDA',layerColorMap='gray'):
    #Check for running mdaVisualisation threads and remove those
    for thread in [item['Thread'] for item in shared_data.RTAnalysisQueuesThreads]:
        if thread.analysisInfo == 'mdaVisualisation':
            #Find the thread/queue:
            for item in shared_data.RTAnalysisQueuesThreads:
                if item['Thread'] == thread:
                    #Remove the thread
                    if item['Thread'] and item['Thread'].is_alive():
                        # Signal the thread to stop (using an event, for example)
                        item['Thread'].stop_signal.set()
                        item['Thread'].join(timeout=1) # Wait for it to finish
                    #Remove the queue
                    if item['Queue']:
                        # Clear the queue
                        while item['Queue']:
                            try:
                                item['Queue'].popleft()
                            except IndexError: # For deque
                                break
                    #remove from shared_data entry
                    shared_data.RTAnalysisQueuesThreads.remove(item)
                    logging.debug('removed old mdaVisualisation thread')
                    break
    
    #Set the latest layer name to be the layer name
    shared_data.newestLayerName = layerName
    #Create an analysis thread which runs this MDA visualisation
    #2024-10-16 refactor attempt: next line isn't needed --> maybe image_queue_analysis isn't needed?
    # create_analysis_thread(shared_data,analysisInfo='mdaVisualisation',createNewThread=False,throughputThread=shared_data._mdamodeNapariHandler.image_queue_analysis) #type: ignore
    #Start a worker dedicated to running the mda mode visualisation
    shared_data._mdamodeNapariHandler.visualisation_worker = shared_data._mdamodeNapariHandler.run_napariVisualisation_worker(shared_data._mdamodeNapariHandler,layerName = layerName,layerColorMap=layerColorMap)
    shared_data._mdamodeNapariHandler.visualisation_worker.finished.connect(_on_worker_fully_stopped_mda)

def _on_worker_fully_stopped_mda():
    logging.debug("MDA worker is confirmed DEAD.")
    shared_data._mdamodeNapariHandler.visualisation_worker = None

def stopMDAVisualisation(shared_data,layerName='Live'):
    if shared_data._mdamodeNapariHandler.visualisation_worker is not None:
        shared_data._mdamodeNapariHandler.visualisation_worker.yielded.disconnect()
        shared_data._mdamodeNapariHandler.visualisation_worker.quit()
        shared_data._mdamodeNapariHandler._new_image.set()

def layer_removed_event_callback(event, shared_data):
    #The name of the layer that is being removed:
    layerRemoved = shared_data.napariViewer.layers[event.index].name
    #Find this layer in the analysis threads
    for thread in [item['Thread'] for item in shared_data.RTAnalysisQueuesThreads]:
        if thread.visualisationObject is not None: 
            if thread.visualisationObject.napariOverlay.layer.name == layerRemoved:
                #Find the thread/queue:
                for item in shared_data.RTAnalysisQueuesThreads:
                    if item['Thread'] == thread:
                        #Remove the thread
                        if item['Thread']:
                            # Signal the thread to stop (using an event, for example)
                            item['Thread'].destroy()
                        #Remove the queue
                        if item['Queue']:
                            # Clear the queue
                            while item['Queue']:
                                try:
                                    item['Queue'].popleft()
                                except IndexError: # For deque
                                    break
                        #remove from shared_data entry
                        shared_data.RTAnalysisQueuesThreads.remove(item)
                        logging.debug('removed rtanalysis thread')
                        break
                
                
                # if 'skipAnalysisThreadDeletion' in vars(shared_data):
                #     if not shared_data.skipAnalysisThreadDeletion:
                #         l.destroy()
                #     else:
                #         shared_data.skipAnalysisThreadDeletion = False
                # else:
                #     l.destroy()
#endregion

def runNapariPycroManager(sMM_JSON,sshared_data,includecustomUI:bool = False,include_flowChart_automatedMicroscopy:bool = True):
    #Go from self to global variables
    global core, MM_JSON, livestate, napariViewer, shared_data
    # core = score
    MM_JSON = sMM_JSON
    livestate = False
    shared_data = sshared_data
    shared_data.register_perf_thread_label(get_native_id(), 'GUI main thread')

    if shared_data.MILcore is not None:
        #Get some info from core to put in shared_data
        shared_data._defaultFocusDevice = shared_data.MILcore.get_focus_device()
        logging.debug(f"Default focus device set to {shared_data._defaultFocusDevice}")
    else:
        logging.warning("MILcore is None, cannot set default focus device.")
        
    #Run the UI on a second thread (hopefully robustly)
    #Napari start
    napariViewer = napari.Viewer()
    #TODO: add fullscreen flag
    # if config.ui.FULLSCREEN:
    napariViewer.window._qt_window.showMaximized()

    # napariViewer._window._qt_viewer.canvas.view._transform.scale=[2,2,2,2]
    #Add a connect event if a layer is removed - to stop background processes
    napariViewer.layers.events.removing.connect(lambda event: layer_removed_event_callback(event,shared_data))
    shared_data.napariViewer = napariViewer
    
    # create_analysis_thread(shared_data,analysisInfo='LiveModeVisualisation',createNewThread=False,throughputThread=shared_data._livemodeNapariHandler.image_queue_analysis)
    # create_analysis_thread(shared_data,analysisInfo='mdaVisualisation',createNewThread=False,throughputThread=shared_data._mdamodeNapariHandler.image_queue_analysis)
    logging.debug("Live mode pseudo-analysis thread created")
    
    #Set some common things for the UI (scale bar on and such)
    InitateNapariUI(napariViewer)

    # --- Developer: "Reload Custom Nodes" menu item -------------------------
    def _reload_custom_nodes():
        from glados_pycromanager.plugins.discovery import reload_all_node_modules
        n, failures = reload_all_node_modules()
        msg = f"Reloaded {n} node module(s)."
        if failures:
            msg += f" {len(failures)} failure(s) — see log."
        logging.info(msg)
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(None, "Glados — Reload Custom Nodes", msg)

    try:
        from PyQt5.QtWidgets import QAction
        _reload_action = QAction("Reload Glados Custom Nodes", napariViewer.window._qt_window)
        _reload_action.triggered.connect(_reload_custom_nodes)
        # Place action inside the "Glados-PycroManager" plugin sub-menu that napari
        # creates from napari.yaml, falling back to the top-level Plugins menu.
        _glados_submenu = None
        for _act in napariViewer.window.plugins_menu.actions():
            if _act.menu() is not None and 'Glados-PycroManager' in _act.text():
                _glados_submenu = _act.menu()
                break
        if _glados_submenu is not None:
            _glados_submenu.addSeparator()
            _glados_submenu.addAction(_reload_action)
        else:
            napariViewer.window.plugins_menu.addSeparator()
            napariViewer.window.plugins_menu.addAction(_reload_action)
    except Exception as _menu_exc:
        logging.debug("Could not add 'Reload Custom Nodes' menu item: %s", _menu_exc)
    # -------------------------------------------------------------------------

    #Add widgets as wanted
    # custom_widget_analysisThreads = dockWidget_analysisThreads()
    # napariViewer.window.add_dock_widget(custom_widget_analysisThreads, area="top", name="Real-time analysis",tabify=True)
    
    #Do something funky for stylesheet re-scaling of pyqt5
    from PyQt5.QtWidgets import QStyle
    defaultFontSize = 14#QWidget().font().pointSize()
    defaultPadding = 1#QWidget().style().pixelMetric(QStyle.PM_DefaultFrameWidth)
    defaultSpacingH = QWidget().style().pixelMetric(QStyle.PM_LayoutHorizontalSpacing)
    defaultSpacingV = QWidget().style().pixelMetric(QStyle.PM_LayoutVerticalSpacing)
    
    
    defaultLeftMargin = QWidget().style().pixelMetric(QStyle.PM_LayoutLeftMargin)
    defaultRightMargin = QWidget().style().pixelMetric(QStyle.PM_LayoutRightMargin)
    defaultTopMargin = QWidget().style().pixelMetric(QStyle.PM_LayoutTopMargin)
    defaultBottomMargin = QWidget().style().pixelMetric(QStyle.PM_LayoutBottomMargin)
    
    
    
    defaultSpacing=defaultSpacingH
    # Create a custom stylesheet with a scaling factor
    
    scaleFactor = 0.75
    shared_data.GUIscaleFactor = scaleFactor
    useStyleSheet = True
    ScaledStylesheetOld = f"""
    QWidget {{
        font-size: {int(defaultFontSize*scaleFactor)}px;
        padding: {int(defaultSpacingH*scaleFactor)}px {int(defaultSpacingV*scaleFactor)}px;
    }}
    
    QPushButton {{
        padding: {int(defaultPadding * scaleFactor)}px {int(defaultPadding * scaleFactor)}px;
        min-height: {int(20 * scaleFactor)}px; 
        min-width: {int(20 * scaleFactor)}px; 
    }}
    QLineEdit {{
        border-width: {int(0*scaleFactor)}px {int(0*scaleFactor)}px;
        padding: {int(defaultPadding*scaleFactor)}px {int(defaultPadding*scaleFactor)}px;
        margin: {int(0*scaleFactor)}px {int(0*scaleFactor)}px;min-height: {int(20 * scaleFactor)}px; 
    }}
    QCheckBox::indicator {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    QAbstractButton::icon {{
        width: {int(16 * scaleFactor)}px; 
        height: {int(16 * scaleFactor)}px; 
    }}
    QComboBox {{
        padding: {int(defaultPadding*scaleFactor)}px {int(defaultSpacing*scaleFactor)}px;
        min-height: {int(20 * scaleFactor)}px;
        min-width: {int(20 * scaleFactor)}px; 
    }}
    QComboBox::down-arrow {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    """

    # padding: {int(defaultSpacingH/2*scaleFactor)}px {int(defaultSpacingV/2*scaleFactor)}px;
    ScaledStylesheet = f"""
    QWidget {{
        font-size: {int(defaultFontSize*scaleFactor)}px;
        padding: {int(defaultSpacingH*scaleFactor)}px {int(defaultSpacingV*scaleFactor)}px;
        margin: {int(defaultTopMargin/4*scaleFactor)}px {int(defaultRightMargin/4*scaleFactor)}px {int(defaultBottomMargin/4*scaleFactor)}px {int(defaultLeftMargin/4*scaleFactor)}px;
    }}
    QLineEdit {{
        border-width: {int(4*scaleFactor)}px {int(4*scaleFactor)}px;
        min-height: {int(25 * scaleFactor)}px; 
        min-width: {int(25 * scaleFactor)}px; 
    }}
    QCheckBox::indicator {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    QAbstractButton::icon {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    QComboBox::down-arrow {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    QComboBox{{
        min-height: {int(25 * scaleFactor)}px; 
        min-width: {int(25 * scaleFactor)}px; 
    }}
    QCheckBox{{
        min-height: {int(25 * scaleFactor)}px; 
        min-width: {int(25 * scaleFactor)}px; 
    }}
    QGroupBox {{
        margin: 0px;
        padding: 0px;
        spacing: 0px;
    }}
    QVBoxLayout {{
        spacing: 0px;
    }}
    """

    logging.debug('In runNapariPycroManager')
    
    custom_widget_MMcontrols = dockWidget_MMcontrol()
    # Apply the stylesheet
    if useStyleSheet:
        custom_widget_MMcontrols.setStyleSheet(ScaledStylesheet)
    #Add to napari
    napariViewer.window.add_dock_widget(custom_widget_MMcontrols, area="top", name="Controls",tabify=True)
    
    custom_widget_MDA = dockWidget_MDA()
    if useStyleSheet:
        custom_widget_MDA.setStyleSheet(ScaledStylesheet)
    napariViewer.window.add_dock_widget(custom_widget_MDA, area="top", name="Multi-D acquisition",tabify=True)
    
    if include_flowChart_automatedMicroscopy:
        custom_widget_flowChart = dockWidget_flowChart()
        if useStyleSheet:
            custom_widget_flowChart.setStyleSheet(ScaledStylesheet)
        napariViewer.window.add_dock_widget(custom_widget_flowChart, area="top", name="Autonomous microscopy",tabify=True)
        custom_widget_flowChart.dockWidget.focus()
    
    if includecustomUI:
        gladosLaserInfo = dockWidget_fullGladosUI()
        if not gladosLaserInfo.criticalErrors:
            napariViewer.window.add_dock_widget(gladosLaserInfo, area="right", name="GladosUI")
        else:
            logging.warning("GladosUI (specific for Endesfelder lab) not added due to critical errors")

    #Performance Mode is a diagnostic tool, not opened by default. Users open it
    #on demand via Plugins > Glados-PycroManager > Performance Mode.

    # Force the "Controls" widget to the front
    custom_widget_MMcontrols.parent().raise_()
    #Sketchy way to set initial height
    #TODO: set config tab height
    custom_widget_MMcontrols.parent().setFixedHeight(400)#config.ui.WIDGET_TAB_HEIGHT)
    QApplication.processEvents()
    custom_widget_MMcontrols.parent().setMinimumHeight(0)
    custom_widget_MMcontrols.parent().setMaximumHeight(16777215)
    
    returnInfo = {}
    returnInfo['napariViewer'] = napariViewer
    returnInfo['MMcontrolWidget'] = custom_widget_MMcontrols.getDockWidget()
    
    # breakpoint
    return returnInfo