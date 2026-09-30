"""T-D8: the NDTiff frame writer, against a real `ndstorage.NDTiffDataset`.

`FrameWriter` carries the queue, backpressure and drain semantics pinned in
`test_frame_writer.py`; these tests pin only what `NDTiffFrameWriter` adds: frames
land in a dataset that reads back at the right coordinates with their metadata,
metadata that JSON cannot encode does not cost the frame, and the queue is sized
from the frame size it is told rather than from a target that cannot describe it.
"""
from __future__ import annotations

import contextlib
import io

import numpy as np
import pytest

ndstorage = pytest.importorskip("ndstorage")

from glados_pycromanager.GUI.frame_writer import (  # noqa: E402
    MIN_CAPACITY,
    FrameWriter,
    NDTiffFrameWriter,
    ZarrFrameWriter,
    json_safe_metadata,
)


def _open(path):
    with contextlib.redirect_stdout(io.StringIO()):  # the reader prints a progress bar
        return ndstorage.NDTiffDataset(str(path))


def _frame(value, shape=(32, 48)):
    return np.full(shape, value, dtype=np.uint16)


def test_frames_land_at_their_coordinates(tmp_path):
    target = tmp_path / "acq"
    dataset = ndstorage.NDTiffDataset(str(target), summary_metadata={}, writable=True)
    writer = NDTiffFrameWriter(dataset, frame_nbytes=32 * 48 * 2)
    writer.start()
    for t in range(3):
        for c, name in enumerate(["DAPI", "FITC"]):
            writer.submit(({"time": t, "channel": name}, {"t": t, "c": c}), _frame(10 * t + c))
    stats = writer.close(timeout=10)
    dataset.finish()
    dataset.close()

    assert stats["written"] == 6 and stats["failed"] == 0
    reader = _open(target)
    try:
        image = reader.read_image(time=2, channel="FITC")
        assert image.shape == (32, 48) and int(image[0, 0]) == 21
        assert reader.read_metadata(time=2, channel="FITC") == {"t": 2, "c": 1}
        assert reader.as_array(axes=["time", "channel"]).shape == (3, 2, 32, 48)
    finally:
        reader.close()


def test_unencodable_metadata_does_not_cost_the_frame(tmp_path):
    class NotJson:
        def __str__(self):
            return "event<t=0>"

    target = tmp_path / "acq"
    dataset = ndstorage.NDTiffDataset(str(target), summary_metadata={}, writable=True)
    writer = NDTiffFrameWriter(dataset, frame_nbytes=32 * 48 * 2)
    writer.start()
    writer.submit(({"time": 0}, {"mda_event": NotJson(), "Exposure": np.float64(5.0)}), _frame(1))
    stats = writer.close(timeout=10)
    dataset.finish()
    dataset.close()

    assert stats["written"] == 1 and stats["failed"] == 0
    reader = _open(target)
    try:
        assert reader.read_metadata(time=0) == {"mda_event": "event<t=0>", "Exposure": 5.0}
    finally:
        reader.close()


def test_json_safe_metadata_leaves_encodable_values_alone():
    assert json_safe_metadata({"a": 1, "b": [1.5, "x"], "c": {"d": None}}) == {
        "a": 1, "b": [1.5, "x"], "c": {"d": None}}
    assert json_safe_metadata(None) == {}


def test_capacity_comes_from_the_frame_size_it_is_told():
    budget = 64 * 1024 * 1024
    small = NDTiffFrameWriter(object(), frame_nbytes=512 * 512 * 2, memory_budget_bytes=budget)
    large = NDTiffFrameWriter(object(), frame_nbytes=2048 * 2048 * 2, memory_budget_bytes=budget)
    assert small.capacity == 128
    assert large.capacity == 8
    assert NDTiffFrameWriter(object(), frame_nbytes=10**12).capacity == MIN_CAPACITY


def test_both_writers_share_one_implementation():
    assert issubclass(ZarrFrameWriter, FrameWriter)
    assert issubclass(NDTiffFrameWriter, FrameWriter)
    for name in ("submit", "close", "stats", "_run", "start"):
        assert name not in vars(ZarrFrameWriter) and name not in vars(NDTiffFrameWriter)
