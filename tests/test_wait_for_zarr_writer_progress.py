"""_wait_for_zarr_writer_progress guards against a real napari crash.

zarr's LocalStore is not atomic: writing a chunk truncates the file to 0
bytes on open, then writes the bytes. `_preinit_mda_zarr` pre-creates the
multiDstack store before run_mda() starts (MMCORE_PLUS fast acquisitions),
and the display path then calls napari's own `add_image()` against that
store -- which makes napari read the array at its current dims.point
(all-zeros for a brand new layer) on its own async thread pool, practically
immediately. If the ZarrFrameWriter thread is still mid-write of that exact
chunk, napari's slicer reads a 0-byte file and crashes with "cannot reshape
array of size 0 into shape (...)", on a thread Glados cannot catch anything
on.

These tests pin the wait helper in isolation: it must return immediately
when there is no writer or one has already completed a write, block while
nothing has been written yet, and give up (logging, not raising) past its
timeout rather than hang forever.
"""
from __future__ import annotations

import threading
import time

from glados_pycromanager.GUI.napariGlados import (
    ZARR_WRITER_FIRST_WRITE_POLL_S,
    _wait_for_zarr_writer_progress,
)


class _StubWriter:
    def __init__(self, last_written_tag=None):
        self.last_written_tag = last_written_tag


class _StubSharedData:
    def __init__(self, writer=None):
        self.zarrFrameWriter = writer


def test_returns_immediately_with_no_writer():
    shared_data = _StubSharedData(writer=None)
    start = time.monotonic()
    _wait_for_zarr_writer_progress(shared_data, timeout_s=1.0)
    assert time.monotonic() - start < 0.1


def test_returns_immediately_once_a_write_already_landed():
    shared_data = _StubSharedData(writer=_StubWriter(last_written_tag=(0, 0)))
    start = time.monotonic()
    _wait_for_zarr_writer_progress(shared_data, timeout_s=1.0)
    assert time.monotonic() - start < 0.1


def test_blocks_until_the_first_write_lands():
    writer = _StubWriter(last_written_tag=None)
    shared_data = _StubSharedData(writer=writer)

    def _land_the_write_soon():
        time.sleep(ZARR_WRITER_FIRST_WRITE_POLL_S * 3)
        writer.last_written_tag = (0, 0)

    threading.Thread(target=_land_the_write_soon).start()

    start = time.monotonic()
    _wait_for_zarr_writer_progress(shared_data, timeout_s=2.0)
    elapsed = time.monotonic() - start

    assert writer.last_written_tag == (0, 0)
    assert elapsed >= ZARR_WRITER_FIRST_WRITE_POLL_S


def test_gives_up_after_the_timeout_instead_of_hanging():
    writer = _StubWriter(last_written_tag=None)  # never lands a write
    shared_data = _StubSharedData(writer=writer)

    start = time.monotonic()
    _wait_for_zarr_writer_progress(shared_data, timeout_s=0.05)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0  # gave up, did not hang
