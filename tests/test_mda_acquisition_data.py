"""T-D6: the finished-acquisition data and storage path must resolve for real.

`MDA_acq_finished` used to fall back to
`zarr.open(shared_data.mdaZarrData['MDA'])`. That cannot work: the dict holds an
already-open `zarr.Array`, not a store path, and zarr 3.x raises
`TypeError: Unsupported type for store_like: 'Array'` for one — which the
`except (KeyError, Exception)` immediately below swallowed. So `self.data` was
None after *every* MMCORE_PLUS acquisition and every downstream Nodz node
consuming `variablesNodz['data']` got None.

The sibling bug: `storage_path` read `self.data.path`. A `zarr.Array` *has* a
`.path`, but it is the array's path inside its store (`''` for a root array),
not a filesystem location.
"""
from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

import numpy as np
import pytest
import zarr

from glados_pycromanager.Core.MDAGlados import MDAGlados


# MDAGlados is a Qt widget, so it cannot be instantiated headlessly. Both
# helpers only read plain attributes off `self`, so call them unbound with a
# stand-in -- which also keeps these tests honest about exactly what they touch.
def _resolve(shared_data):
    return MDAGlados._resolve_finished_acquisition_data(
        SimpleNamespace(shared_data=shared_data)
    )


def _storage_path(**attrs):
    return MDAGlados._acquisition_storage_path(SimpleNamespace(**attrs))


def _shared(datasets=None, zarr_data=None, layer_name=""):
    return SimpleNamespace(
        mdaDatasets=[] if datasets is None else datasets,
        mdaZarrData={} if zarr_data is None else zarr_data,
        newestLayerName=layer_name,
    )


@pytest.fixture
def zarr_array():
    with tempfile.TemporaryDirectory() as tmp:
        yield zarr.open(tmp, shape=(2, 3, 4), chunks=(1, 3, 4), dtype=np.uint16)


# ---- _resolve_finished_acquisition_data ----------------------------------


def test_ndtiff_dataset_wins_when_present():
    dataset = object()
    assert _resolve(_shared(datasets=[object(), dataset])) is dataset


def test_zarr_array_is_returned_as_is_not_reopened(zarr_array):
    """The regression: re-opening it raised TypeError and yielded None."""
    shared = _shared(zarr_data={"MDA": zarr_array}, layer_name="MDA")
    assert _resolve(shared) is zarr_array


def test_reopening_the_array_would_still_fail(zarr_array):
    """Pins *why* the array must be used directly, not re-opened."""
    with pytest.raises(TypeError):
        zarr.open(zarr_array)


def test_the_zarr_entry_is_keyed_by_layer_name_not_the_literal_MDA(zarr_array):
    """A Nodz-driven acquisition names the layer after its node."""
    shared = _shared(zarr_data={"MyNode": zarr_array}, layer_name="MyNode")
    assert _resolve(shared) is zarr_array


def test_none_when_nothing_was_captured(caplog):
    with caplog.at_level("WARNING"):
        assert _resolve(_shared(layer_name="MDA")) is None
    assert any("not accessible" in r.getMessage() for r in caplog.records)


def test_a_missing_mdaDatasets_attribute_is_not_an_error(zarr_array):
    shared = _shared(zarr_data={"MDA": zarr_array}, layer_name="MDA")
    del shared.mdaDatasets
    assert _resolve(shared) is zarr_array


# ---- _acquisition_storage_path -------------------------------------------


def test_storage_path_of_a_zarr_array_is_its_store_root_not_its_in_store_path(
    zarr_array,
):
    path = _storage_path(
        data=zarr_array, storage_folder="C:/nope", storage_file_name="nope"
    )

    assert zarr_array.path == ""  # the trap: truthy-looking attribute, empty value
    assert path == str(zarr_array.store.root)
    assert os.path.isdir(path)


def test_storage_path_of_an_ndtiff_dataset_is_its_path():
    dataset = SimpleNamespace(path="D:/acq/run_1")
    assert (
        _storage_path(data=dataset, storage_folder="C:/nope", storage_file_name="nope")
        == "D:/acq/run_1"
    )


def test_storage_path_falls_back_to_the_expected_path_without_data():
    assert (
        _storage_path(data=None, storage_folder="C:/acq", storage_file_name="run")
        == "C:/acq" + os.sep + "run_1//"
    )
