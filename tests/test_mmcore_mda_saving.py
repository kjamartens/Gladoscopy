"""A pymmcore-plus MDA must actually save the user's data.

The `MMCORE_PLUS` branch of `run_MILCoreAcquisition_worker` used to ignore the
Storage folder entirely: `savefolder`/`savename` were computed and never read,
the `pyMMCdataset` NDTiff store was created and never written to, and the only
copy of the frames was the scratch zarr in a `TemporaryDirectory` that
`release_all_temp_dirs()` deletes on exit. So the acquisition saved nothing,
anywhere. The pycromanager branches beside it were fine because they have an
NDTiff engine; this backend has none, so pymmcore-plus does the recording via
`run_mda(output=...)`.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from glados_pycromanager.GUI.napariGlados import (
    MMCORE_SAVE_SUFFIXES,
    mmcore_output_path,
)


def _shared(fmt="ome-zarr"):
    return SimpleNamespace(
        config=SimpleNamespace(mda_config=SimpleNamespace(mmcore_save_format=fmt))
    )


@pytest.mark.parametrize("fmt,suffix", sorted(MMCORE_SAVE_SUFFIXES.items()))
def test_the_format_setting_picks_the_suffix(fmt, suffix, tmp_path):
    path = mmcore_output_path(_shared(fmt), str(tmp_path), "run")

    assert path == tmp_path / f"run{suffix}"


def test_suffixes_are_ones_pymmcore_plus_can_infer_a_writer_from(tmp_path):
    """`handler_for_path` dispatches on the extension and raises on anything
    else, so these are not free-form strings.

    Also the canary for pymmcore-plus' migration off `mda.handlers` to
    `ome-writers`: if these suffixes stop resolving, this fails instead of MDAs
    silently saving nothing again.

    tmp_path, not a relative name -- some writers create their target eagerly.
    """
    from pymmcore_plus.mda.handlers import handler_for_path

    for suffix in MMCORE_SAVE_SUFFIXES.values():
        assert handler_for_path(str(tmp_path / f"acq{suffix}")) is not None


def test_none_means_acquire_without_saving(tmp_path):
    """The old behaviour has to stay reachable, but only on purpose."""
    assert mmcore_output_path(_shared("none"), str(tmp_path), "run") is None


def test_no_storage_folder_means_no_saving(tmp_path):
    assert mmcore_output_path(_shared(), "", "run") is None
    assert mmcore_output_path(_shared(), None, "run") is None


def test_a_missing_storage_folder_is_created(tmp_path):
    target = tmp_path / "does" / "not" / "exist"

    path = mmcore_output_path(_shared(), str(target), "run")

    assert target.is_dir()
    assert path == target / "run.ome.zarr"


def test_an_existing_acquisition_is_never_overwritten(tmp_path):
    """Same reflex pycromanager has when an acquisition name is reused."""
    first = mmcore_output_path(_shared(), str(tmp_path), "run")
    first.mkdir()

    second = mmcore_output_path(_shared(), str(tmp_path), "run")
    second.mkdir()
    third = mmcore_output_path(_shared(), str(tmp_path), "run")

    assert first.name == "run.ome.zarr"
    assert second.name == "run_1.ome.zarr"
    assert third.name == "run_2.ome.zarr"


def test_a_missing_name_still_produces_a_path(tmp_path):
    assert mmcore_output_path(_shared(), str(tmp_path), "").name == "MDA.ome.zarr"
    assert mmcore_output_path(_shared(), str(tmp_path), None).name == "MDA.ome.zarr"


def test_an_unwritable_storage_folder_degrades_to_not_saving(tmp_path):
    """Better to acquire unsaved and say so than to crash mid-run."""
    blocker = tmp_path / "afile"
    blocker.write_text("not a directory")

    assert mmcore_output_path(_shared(), str(blocker / "sub"), "run") is None


# -- the end-to-end check, against pymmcore-plus' own demo camera ----------

@pytest.mark.slow
@pytest.mark.parametrize("fmt", ["ome-zarr", "ome-tiff"])
def test_a_demo_mda_really_lands_on_disk(fmt, tmp_path):
    """No microscope required: pymmcore-plus ships a demo camera, so the actual
    claim -- 'the data saves' -- is testable rather than merely reasoned about."""
    import useq
    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    core.loadSystemConfiguration()
    sequence = useq.MDASequence(
        time_plan={"interval": 0, "loops": 3},
        channels=[{"config": "DAPI", "exposure": 1}],
        z_plan={"range": 1, "step": 1},
    )
    expected_frames = len(list(sequence))

    output = mmcore_output_path(_shared(fmt), str(tmp_path), "demo")
    seen = []
    core.mda.events.frameReady.connect(lambda *a: seen.append(1))
    core.run_mda(sequence, output=str(output)).join()
    core.mda.events.frameReady.disconnect()

    assert output.exists(), f"{fmt} MDA wrote nothing to {output}"
    written = (sum(f.stat().st_size for f in output.rglob("*") if f.is_file())
               if output.is_dir() else output.stat().st_size)
    assert written > 0
    # Glados' own display/analysis hook must keep working alongside the writer.
    assert len(seen) == expected_frames


@pytest.mark.slow
def test_the_saved_data_reads_back_with_the_acquisition_shape(tmp_path):
    """Saving something is not enough; it has to be the acquisition."""
    import useq
    import zarr
    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    core.loadSystemConfiguration()
    sequence = useq.MDASequence(
        time_plan={"interval": 0, "loops": 4},
        channels=[{"config": "DAPI", "exposure": 1},
                  {"config": "FITC", "exposure": 1}],
        z_plan={"range": 2, "step": 1},
    )

    output = mmcore_output_path(_shared("ome-zarr"), str(tmp_path), "shape")
    core.run_mda(sequence, output=str(output)).join()

    group = zarr.open(str(output), mode="r")
    array = next(iter(group.arrays()))[1]
    # 4 timepoints x 2 channels x 3 z, then the frame plane.
    assert array.shape[:3] == (4, 2, 3)
    assert array.shape[-2:] == (core.getImageHeight(), core.getImageWidth())
    assert array[3, 1, 2].any(), "last frame of the plan is empty"
