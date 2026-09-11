"""T-D8: a pymmcore-plus MDA can be archived as NDTiff, written by Glados itself.

pymmcore-plus has no NDTiff sink, so `run_mda(output=...)` cannot produce one. With
the `ndtiff` save format the MDA worker opens an `NDTiffDataset`, the frameReady
callback queues every frame to an `NDTiffFrameWriter` (never writing inline on the
MDA thread), and the archive is drained and finished once the acquisition ends.
The dataset then resolves for downstream nodes exactly like a pycromanager one.

The dead store this replaces: `PyMMCore_startedAcqCallback` used to create an
`NDTiffDataset` in a scratch directory on every MDA and never write to it.
"""
from __future__ import annotations

import contextlib
import dataclasses
import inspect
import io
from types import SimpleNamespace

import numpy as np
import pytest
import useq

from glados_pycromanager.Core.MDAGlados import MDAGlados
from glados_pycromanager.GUI import napariGlados
from glados_pycromanager.GUI.napariGlados import (
    MMCORE_NDTIFF_FORMAT,
    MMCORE_SAVE_SUFFIXES,
    finish_ndtiff_store,
    mmcore_output_path,
    ndtiff_coordinates,
    open_ndtiff_store,
    submit_ndtiff_frame,
)
from glados_pycromanager.GUI.sharedFunctions import MDAConfig, Shared_data


def _shared(fmt=MMCORE_NDTIFF_FORMAT):
    return SimpleNamespace(
        config=SimpleNamespace(mda_config=SimpleNamespace(mmcore_save_format=fmt))
    )


def _open_quietly(path):
    from ndstorage import NDTiffDataset

    with contextlib.redirect_stdout(io.StringIO()):  # the reader prints a progress bar
        return NDTiffDataset(str(path))


# ------------------------------------------------------------ the setting


def test_ndtiff_is_offered_and_the_ome_formats_stay():
    field = {f.name: f for f in dataclasses.fields(MDAConfig)}["mmcore_save_format"]
    options = field.metadata["options"]
    assert MMCORE_NDTIFF_FORMAT in options
    for kept in ("ome-zarr", "ome-tiff", "none"):
        assert kept in options, f"{kept} is the interoperable/escape option and must remain"
    assert field.default in options


def test_ndtiff_is_not_a_run_mda_output_suffix():
    """`test_mmcore_mda_saving` checks every suffix resolves to a pymmcore-plus
    writer; NDTiff never would, because Glados writes it."""
    assert MMCORE_NDTIFF_FORMAT not in MMCORE_SAVE_SUFFIXES


# ------------------------------------------------------------ naming


def test_ndtiff_acquisitions_are_numbered_like_pycromanagers(tmp_path):
    first = mmcore_output_path(_shared(), str(tmp_path), "run")
    assert first == tmp_path / "run_1"
    first.mkdir()
    second = mmcore_output_path(_shared(), str(tmp_path), "run")
    assert second == tmp_path / "run_2"


def test_ndtiff_needs_a_storage_folder(tmp_path):
    assert mmcore_output_path(_shared(), "", "run") is None
    assert mmcore_output_path(_shared(), str(tmp_path), "").name == "MDA_1"


# ------------------------------------------------------------ frames


def test_coordinates_use_pycromanager_axis_names_and_channel_names():
    event = useq.MDAEvent(index={"t": 2, "c": 1, "z": 0}, channel={"config": "FITC"})
    assert ndtiff_coordinates(event) == {"time": 2, "channel": "FITC", "z": 0}
    assert ndtiff_coordinates(useq.MDAEvent(index={"t": 3, "p": 1})) == {"time": 3, "position": 1}


def test_the_writer_gets_a_copy_of_the_metadata():
    """The ring consumer mutates the original dict while the writer serialises it."""
    recorded = []
    writer = SimpleNamespace(submit=lambda destination, image: recorded.append(destination) or True)
    metadata = {"exposure_ms": 1.0}
    submit_ndtiff_frame(writer, np.zeros((2, 2), np.uint16), useq.MDAEvent(index={"t": 0}), metadata)
    metadata["Axes"] = {"time": 0}
    coordinates, sent = recorded[0]
    assert coordinates == {"time": 0}
    assert sent == {"exposure_ms": 1.0} and sent is not metadata


# ------------------------------------------------------------ resolution


def test_the_current_acquisitions_dataset_wins_over_an_earlier_one():
    old, new = SimpleNamespace(path="old"), SimpleNamespace(path="new")
    shared = SimpleNamespace(mdaDatasets=[old, new], mdaCurrentDataset=new,
                             mdaZarrData={}, newestLayerName="")
    assert MDAGlados._resolve_finished_acquisition_data(SimpleNamespace(shared_data=shared)) is new


def test_an_acquisition_without_a_dataset_does_not_inherit_the_previous_one():
    """An NDTiff run, then an OME-Zarr run: the second must not report the first's data."""
    scratch = object()
    shared = SimpleNamespace(mdaDatasets=[SimpleNamespace(path="earlier")], mdaCurrentDataset=None,
                             mdaZarrData={"L": scratch}, newestLayerName="L")
    assert MDAGlados._resolve_finished_acquisition_data(SimpleNamespace(shared_data=shared)) is scratch


def test_appending_a_dataset_marks_it_current(tmp_appdata):
    shared = Shared_data()
    assert shared.mdaCurrentDataset is None
    dataset = SimpleNamespace(path="x")
    shared.appendNewMDAdataset(dataset)
    assert shared.mdaCurrentDataset is dataset


# ------------------------------------------------------------ wiring


def test_the_started_callback_no_longer_creates_a_dead_dataset():
    source = inspect.getsource(napariGlados.napariHandler.PyMMCore_startedAcqCallback)
    assert "NDTiffDataset(" not in source
    assert "new_pyMMC_temp_dir" not in source


def test_frame_ready_archives_before_handing_to_the_ring():
    source = inspect.getsource(napariGlados.napariHandler.grab_image_liveVis_PyMMCore)
    assert source.index("submit_ndtiff_frame(") < source.index("self.frame_ring.push(")


def test_the_worker_finishes_the_archive_after_the_ring_and_gives_run_mda_no_output():
    source = inspect.getsource(napariGlados)
    disconnect = source.index("frameReady.disconnect(connected_callback)")
    assert source.index("self._stop_frame_ring_consumer()", disconnect) < source.index(
        "self._finish_ndtiff_store()", disconnect)
    assert "output=str(output_path) if output_path and not ndtiff_output else None" in source
    assert source.index("self._open_ndtiff_store(output_path)") < source.index(
        "run_mda(\n                            mda_sequence_useq")


# ------------------------------------------------------------ end to end


@pytest.mark.slow
def test_a_demo_mda_is_archived_as_ndtiff_at_the_acquisition_shape(tmp_path):
    """Against pymmcore-plus' demo camera, through the helpers the worker uses."""
    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    core.loadSystemConfiguration()
    sequence = useq.MDASequence(
        time_plan={"interval": 0, "loops": 4},
        channels=[{"config": "DAPI", "exposure": 1}, {"config": "FITC", "exposure": 1}],
        z_plan={"range": 2, "step": 1},
    )
    h, w = core.getImageHeight(), core.getImageWidth()
    path = mmcore_output_path(_shared(), str(tmp_path), "demo")
    dataset, writer = open_ndtiff_store(path, w * h * core.getBytesPerPixel())

    seen = []

    def on_frame(image, event, metadata):
        seen.append(1)
        submit_ndtiff_frame(writer, image, event, metadata)

    core.mda.events.frameReady.connect(on_frame)
    core.run_mda(sequence).join()  # no output: Glados writes the NDTiff, not pymmcore-plus
    core.mda.events.frameReady.disconnect(on_frame)
    finish_ndtiff_store(dataset, writer)

    assert len(seen) == len(list(sequence)) == 24, "frameReady must still fire for every frame"
    assert writer.stats()["written"] == 24 and writer.stats()["dropped"] == 0

    reader = _open_quietly(path)
    try:
        assert reader.as_array(axes=["time", "channel", "z"]).shape == (4, 2, 3, h, w)
        assert np.asarray(reader.read_image(time=3, channel="FITC", z=2)).any(), "last frame is empty"
        assert reader.read_metadata(time=3, channel="FITC", z=2), "frame metadata was not stored"
    finally:
        reader.close()
    assert len([p for p in path.iterdir() if p.is_file()]) <= 3, "NDTiff should not be one file per frame"
