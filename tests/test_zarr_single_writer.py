"""T-D2: each frame reaches the multiDstack store exactly once.

On MMCORE_PLUS the same frame used to be written twice -- once from the
acquisition side (`_try_write_frame_to_zarr`, which exists because the vis
queue drops frames and a dropped frame there is a permanently black slice) and
again from the GUI thread in `_napariUpdateLive_locked`, with the slice index
recomputed identically. The second write is a full chunk re-encode of data that
is already in the store, paid for on the thread that must stay free to paint.

The acquisition-side write now stamps the metadata dict it wrote with the index
it used (`ZARR_WRITTEN_SLICE_KEY`); the display path skips its own write when
that stamp is present. The stamp is a per-frame fact rather than a per-backend
guess, so the pycromanager paths -- which do no acquisition-side write at all --
and any frame whose ring write raised keep writing from the display path.
"""
from __future__ import annotations

import numpy as np

import glados_pycromanager.GUI.napariGlados as napariGlados
from glados_pycromanager.GUI.napariGlados import ZARR_WRITTEN_SLICE_KEY, _create_mda_zarr
from glados_pycromanager.GUI.sharedFunctions import Shared_data


def _handler(shared_data):
    """A napariHandler without its __init__: that wants a live napari viewer,
    and none of it is what these tests are about."""
    handler = object.__new__(napariGlados.napariHandler)
    handler.shared_data = shared_data
    handler._zarr_writer = None
    return handler


def _write(handler, image, metadata):
    """Write one frame and wait for it to actually land.

    Since T-D3 `_try_write_frame_to_zarr` only *queues* the write -- it hands the
    frame to `ZarrFrameWriter` so disk latency is not charged to the frame-ring
    consumer -- so a test that reads the array back has to drain the writer
    first, exactly as the acquisition teardown does before the finalisation pass
    reads the store.
    """
    handler._try_write_frame_to_zarr(image, metadata)
    handler._stop_zarr_writer()


def _shared_data_with_store(n_time=3, h=4, w=5):
    shared_data = Shared_data()
    shared_data._mdaModeParams = [{"axes": {"time": i}} for i in range(n_time)]
    shared_data.newestLayerName = "MDA"
    _create_mda_zarr(shared_data, "MDA", [n_time], h, w, np.uint16)
    return shared_data


def test_successful_write_stamps_the_slice_it_used(tmp_appdata):
    shared_data = _shared_data_with_store()
    metadata = {"Axes": {"time": 2}}

    _write(_handler(shared_data), np.full((4, 5), 7, dtype=np.uint16), metadata)

    assert metadata[ZARR_WRITTEN_SLICE_KEY] == (2,)
    assert np.array_equal(shared_data.mdaZarrData["MDA"][2], np.full((4, 5), 7))


def test_a_failed_write_leaves_no_stamp(tmp_appdata):
    """The display path is then the only writer left, so it must not be told to
    skip. A frame whose Axes do not match the acquisition's dimensions raises
    inside the helper, which swallows it at DEBUG."""
    shared_data = _shared_data_with_store()
    metadata = {"Axes": {}}  # no 'time' -> KeyError on the dimension lookup

    _write(_handler(shared_data), np.zeros((4, 5), dtype=np.uint16), metadata)

    assert ZARR_WRITTEN_SLICE_KEY not in metadata


def test_no_stamp_when_there_is_no_store_yet(tmp_appdata):
    """The pre-store race: frames arriving before the array exists return early."""
    shared_data = Shared_data()
    shared_data._mdaModeParams = [{"axes": {"time": 0}}]
    shared_data.newestLayerName = "MDA"
    metadata = {"Axes": {"time": 0}}

    _write(_handler(shared_data), np.zeros((4, 5), dtype=np.uint16), metadata)

    assert ZARR_WRITTEN_SLICE_KEY not in metadata


def test_the_stamp_survives_metadata_refactor(tmp_appdata):
    """The display path reads the stamp *after* re-refactoring the metadata, so
    the stamp only works because metadata_refactor mutates in place."""
    from glados_pycromanager.GUI import utils

    shared_data = _shared_data_with_store()
    metadata = {"Axes": {"time": 1}}
    _write(_handler(shared_data), np.zeros((4, 5), dtype=np.uint16), metadata)

    refactored = utils.metadata_refactor(metadata, shared_data)

    assert refactored[ZARR_WRITTEN_SLICE_KEY] == (1,)


def test_the_stamp_is_the_index_actually_written(tmp_appdata):
    """The display path steps the napari dims sliders to the stamped index, so a
    stamp that disagreed with the write would show the wrong slice."""
    shared_data = _shared_data_with_store(n_time=3)
    handler = _handler(shared_data)

    for time_point in range(3):
        metadata = {"Axes": {"time": time_point}}
        _write(handler, np.full((4, 5), time_point + 1, dtype=np.uint16), metadata)
        written_index = metadata[ZARR_WRITTEN_SLICE_KEY]
        assert np.array_equal(
            shared_data.mdaZarrData["MDA"][written_index],
            np.full((4, 5), time_point + 1),
        )


def test_a_burst_of_frames_all_land_after_teardown(tmp_appdata):
    """T-D3, end to end: the whole point of the writer thread.

    Every frame handed to `_try_write_frame_to_zarr` must be in the store once
    the acquisition teardown has drained the writer -- none dropped, none left
    in flight -- even though the writes happened asynchronously behind it.
    """
    n_time = 40
    shared_data = _shared_data_with_store(n_time=n_time)
    handler = _handler(shared_data)

    for time_point in range(n_time):
        handler._try_write_frame_to_zarr(
            np.full((4, 5), time_point + 1, dtype=np.uint16),
            {"Axes": {"time": time_point}},
        )
    handler._stop_zarr_writer()          # what the acquisition teardown does

    store = shared_data.mdaZarrData["MDA"]
    for time_point in range(n_time):
        assert np.array_equal(store[time_point],
                              np.full((4, 5), time_point + 1)), \
            f"slice {time_point} did not land"


def test_the_writer_is_retired_when_the_store_is_replaced(tmp_appdata):
    """The dimension-mismatch branch re-creates the store mid-session; a writer
    still pointed at the discarded array would write into nothing."""
    shared_data = _shared_data_with_store()
    handler = _handler(shared_data)
    handler._try_write_frame_to_zarr(np.zeros((4, 5), dtype=np.uint16),
                                     {"Axes": {"time": 0}})
    first_writer = handler._zarr_writer
    assert first_writer is not None

    _create_mda_zarr(shared_data, "MDA", [2], 4, 5, np.uint16)   # new store
    handler._try_write_frame_to_zarr(np.zeros((4, 5), dtype=np.uint16),
                                     {"Axes": {"time": 0}})

    assert handler._zarr_writer is not first_writer
    assert handler._zarr_writer.array is shared_data.mdaZarrData["MDA"]
    assert not first_writer.is_running
    handler._stop_zarr_writer()
