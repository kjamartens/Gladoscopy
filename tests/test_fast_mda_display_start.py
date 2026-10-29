"""The first frames of a fast MDA must not freeze or break the display.

Reported on a 10 ms, 500 time x 3 z MDA (Python backend): the display stuttered
for ~10 s before updating, and one run showed nothing at all. Three causes:

* A multiDstack store left over from an earlier acquisition under the same
  layer name (its layer closed by the user, so nothing released the store) was
  reused by the display path for a plan with a different shape. Every write
  then failed with zarr's ``BoundsCheckError`` and every frame was dropped.
* ``import zarr`` ran on the GUI thread on the first frame (~4 s with the
  acquisition competing for the GIL). It is now pre-imported in the background
  once startup is ready.
* Releasing a store deleted its one-file-per-frame directory on the GUI thread
  (3.3 s for 1500 files on Windows). The directory is now renamed at once and
  deleted on a background thread.
"""
from __future__ import annotations

import os
import threading
import time

import numpy as np

import glados_pycromanager.GUI.napariGlados as napariGlados
import glados_pycromanager.GUI.sharedFunctions as sf
from glados_pycromanager.GUI.sharedFunctions import Shared_data


def _store(shared_data, layer, shape, h=8, w=8, dtype=np.uint16):
    return napariGlados._create_mda_zarr(shared_data, layer, shape, h, w, dtype)


def test_store_of_a_different_plan_is_discarded(tmp_appdata):
    # The user's case: a z-then-time store (3, 500), then the order changed to
    # time-then-z (500, 3) and the old layer was gone.
    shared_data = Shared_data()
    old = _store(shared_data, 'MDA', [3, 500])
    old_dir = shared_data.mdaZarrTempDirs['MDA'].name

    discarded = napariGlados._discard_mismatched_mda_zarr(
        shared_data, 'MDA', (500, 3, 8, 8), np.uint16)

    assert discarded
    assert shared_data.mdaZarrData['MDA'] is None
    assert 'MDA' not in shared_data.mdaZarrTempDirs
    assert not os.path.exists(old_dir)
    assert old.shape == (3, 500, 8, 8)


def test_store_with_a_different_frame_size_or_dtype_is_discarded(tmp_appdata):
    shared_data = Shared_data()
    _store(shared_data, 'MDA', [5])
    assert napariGlados._discard_mismatched_mda_zarr(shared_data, 'MDA', (5, 16, 16), np.uint16)

    _store(shared_data, 'MDA', [5])
    assert napariGlados._discard_mismatched_mda_zarr(shared_data, 'MDA', (5, 8, 8), np.uint8)


def test_matching_store_is_kept(tmp_appdata):
    shared_data = Shared_data()
    store = _store(shared_data, 'MDA', [500, 3])

    assert not napariGlados._discard_mismatched_mda_zarr(
        shared_data, 'MDA', (500, 3, 8, 8), np.uint16)
    assert shared_data.mdaZarrData['MDA'] is store


def test_missing_store_is_left_alone(tmp_appdata):
    shared_data = Shared_data()
    assert not napariGlados._discard_mismatched_mda_zarr(shared_data, 'MDA', (5, 8, 8), np.uint16)


def test_releasing_a_store_does_not_delete_its_files_on_the_calling_thread(tmp_appdata, monkeypatch):
    shared_data = Shared_data()
    store = _store(shared_data, 'MDA', [4])
    for i in range(4):
        store[i] = np.full((8, 8), i, dtype=np.uint16)
    path = shared_data.mdaZarrTempDirs['MDA'].name

    caller = threading.get_ident()
    rmtree_threads = []
    real_rmtree = sf.shutil.rmtree

    def recording_rmtree(p, *a, **k):
        rmtree_threads.append(threading.get_ident())
        return real_rmtree(p, *a, **k)
    monkeypatch.setattr(sf.shutil, 'rmtree', recording_rmtree)

    shared_data.release_zarr_temp_dir('MDA')

    # The old path is free at once ...
    assert not os.path.exists(path)
    # ... and the files go on another thread.
    deadline = time.monotonic() + 10
    while os.path.exists(path + '.discarded') and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not os.path.exists(path + '.discarded')
    assert rmtree_threads and caller not in rmtree_threads


def test_release_all_deletes_synchronously(tmp_appdata):
    # Runs on aboutToQuit, right before os._exit: no thread would survive.
    shared_data = Shared_data()
    _store(shared_data, 'MDA', [3])
    path = shared_data.mdaZarrTempDirs['MDA'].name

    shared_data.release_all_temp_dirs()

    assert not os.path.exists(path)
    assert not os.path.exists(path + '.discarded')


def test_prewarm_imports_zarr_off_the_calling_thread(monkeypatch):
    started = []
    real_thread = napariGlados.Thread

    def recording_thread(*a, **k):
        t = real_thread(*a, **k)
        started.append(t)
        return t
    monkeypatch.setattr(napariGlados, 'Thread', recording_thread)

    napariGlados.prewarm_display_imports()

    assert len(started) == 1 and started[0].daemon
    started[0].join(timeout=60)
    import sys
    assert 'zarr' in sys.modules
