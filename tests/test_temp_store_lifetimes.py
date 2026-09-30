"""T-D7: a scratch store must outlive every reader of it, and no longer.

`tempfile.TemporaryDirectory`'s finalizer rmtree()s its directory, so the
*object* is the store's lifetime. Two bugs followed from ignoring that:

(a) `PyMMCore_startedAcqCallback` wrote
    `str(tempfile.TemporaryDirectory().name)` — constructing the object and
    immediately dropping it, so the directory was deleted and the `os.makedirs`
    below recreated it with nothing owning its cleanup.
(b) `shared_data.mdaZarrTempDir` was a single slot written by two sites, so
    starting a second MDA dropped the first `TemporaryDirectory` and its
    finalizer deleted a store the first acquisition's napari layer was still
    rendering from.
"""
from __future__ import annotations

import gc
import os

from glados_pycromanager.GUI.sharedFunctions import Shared_data


def test_two_layers_keep_two_independent_stores(tmp_appdata):
    """The (b) regression: a second acquisition must not delete the first store."""
    shared_data = Shared_data()

    first = shared_data.new_zarr_temp_dir("MDA")
    second = shared_data.new_zarr_temp_dir("MyNode")

    gc.collect()  # the old single-slot code would have collected `first` here
    assert first.name != second.name
    assert os.path.isdir(first.name)
    assert os.path.isdir(second.name)


def test_recreating_the_same_layer_replaces_its_store(tmp_appdata):
    """That layer's array is being discarded anyway, so its store should go."""
    shared_data = Shared_data()

    first = shared_data.new_zarr_temp_dir("MDA")
    first_path = first.name
    second = shared_data.new_zarr_temp_dir("MDA")

    assert not os.path.exists(first_path)
    assert os.path.isdir(second.name)
    assert list(shared_data.mdaZarrTempDirs) == ["MDA"]


def test_releasing_a_layer_removes_only_that_store(tmp_appdata):
    shared_data = Shared_data()
    kept = shared_data.new_zarr_temp_dir("keep")
    dropped = shared_data.new_zarr_temp_dir("drop")

    shared_data.release_zarr_temp_dir("drop")

    assert not os.path.exists(dropped.name)
    assert os.path.isdir(kept.name)
    assert list(shared_data.mdaZarrTempDirs) == ["keep"]


def test_releasing_an_unknown_layer_is_a_no_op(tmp_appdata):
    shared_data = Shared_data()
    shared_data.release_zarr_temp_dir("never-existed")  # must not raise


def test_the_ndtiff_scratch_directory_survives_its_creation(tmp_appdata):
    """The (a) regression: the directory used to be gone before it was used."""
    shared_data = Shared_data()

    tmpdir = shared_data.new_pyMMC_temp_dir()
    gc.collect()

    assert os.path.isdir(tmpdir.name)
    assert shared_data.pyMMCdatasetTempDir is tmpdir


def test_a_new_acquisition_replaces_the_ndtiff_scratch_directory(tmp_appdata):
    shared_data = Shared_data()
    first_path = shared_data.new_pyMMC_temp_dir().name
    second = shared_data.new_pyMMC_temp_dir()

    assert not os.path.exists(first_path)
    assert os.path.isdir(second.name)


def test_release_all_removes_every_store(tmp_appdata):
    """os._exit(0) on quit runs no finalizers, so this is the only cleanup."""
    shared_data = Shared_data()
    paths = [
        shared_data.new_zarr_temp_dir("a").name,
        shared_data.new_zarr_temp_dir("b").name,
        shared_data.new_pyMMC_temp_dir().name,
    ]

    shared_data.release_all_temp_dirs()

    assert not any(os.path.exists(p) for p in paths)
    assert shared_data.mdaZarrTempDirs == {}
    assert shared_data.pyMMCdatasetTempDir is None


def test_release_all_is_idempotent(tmp_appdata):
    shared_data = Shared_data()
    shared_data.new_zarr_temp_dir("a")
    shared_data.new_pyMMC_temp_dir()

    shared_data.release_all_temp_dirs()
    shared_data.release_all_temp_dirs()  # must not raise


def test_an_already_removed_directory_does_not_break_teardown(tmp_appdata):
    """A store the OS temp sweep (or a user) removed first is not an error."""
    shared_data = Shared_data()
    tmpdir = shared_data.new_zarr_temp_dir("a")
    os.rmdir(tmpdir.name)

    shared_data.release_all_temp_dirs()  # must not raise
    assert shared_data.mdaZarrTempDirs == {}
