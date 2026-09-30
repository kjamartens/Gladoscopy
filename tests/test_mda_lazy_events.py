"""T-H2: the MDA panel keeps `useq.MDASequence` as its plan and converts lazily.

`get_MDA_events_from_GUI` ended every rebuild with
`self.mda = to_pycromanager(self.mda_useq)`, which materialises and
pydantic-validates one event dict per frame -- and on MMCORE_PLUS `run_mda()`
iterates the sequence again anyway. `MDAGlados.mda` is now a property that
converts on first read and caches until the next rebuild, mirroring
`Shared_data._mdaModeParams`, and the acquire paths hand `shared_data` the raw
sequence when nothing has materialised it yet.
"""
from __future__ import annotations

import inspect
import os
import re
from unittest.mock import patch

import pytest

pytest.importorskip("PyQt5.QtWidgets")

import useq  # noqa: E402
import useq.pycromanager  # noqa: E402,F401 -- so mock.patch can target it


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def mda_cls(qapp):
    from glados_pycromanager.Core.MDAGlados import MDAGlados

    return MDAGlados


def _sequence(loops):
    return useq.MDASequence(time_plan={"interval": 0.0, "loops": loops})


@pytest.fixture
def host(mda_cls):
    cls = type(
        "LazyHost",
        (),
        {
            "mda": mda_cls.mda,
            "_mdaEventsForAcquisition": mda_cls._mdaEventsForAcquisition,
        },
    )
    return cls


def _spy():
    return patch(
        "useq.pycromanager.to_pycromanager", wraps=useq.pycromanager.to_pycromanager
    )


# ------------------------------------------------------------ the property


def test_the_rebuild_no_longer_converts(mda_cls):
    source = inspect.getsource(mda_cls.get_MDA_events_from_GUI)
    code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
    assert "to_pycromanager(" not in code
    assert not re.search(r"\{self\.mda\}", code), "an eager f-string would force the conversion"
    assert code.index("self.mda_useq = useq.MDASequence(") < code.index("self._mda = None")


def test_first_read_converts_and_caches(host):
    obj = host()
    obj.mda_useq = _sequence(5)
    obj._mda = None
    with _spy() as spy:
        first = obj.mda
        second = obj.mda
    spy.assert_called_once()
    assert isinstance(first, list) and len(first) == 5
    assert second is first


def test_invalidating_reconverts_the_new_plan(host):
    obj = host()
    obj.mda_useq = _sequence(3)
    obj._mda = None
    assert len(obj.mda) == 3
    obj.mda_useq = _sequence(7)
    obj._mda = None  # what get_MDA_events_from_GUI does
    assert len(obj.mda) == 7


def test_an_explicit_assignment_is_not_converted(host):
    obj = host()
    obj.mda_useq = _sequence(4)
    events = [{"axes": {"time": 0}}]
    with _spy() as spy:
        obj.mda = events
        assert obj.mda is events
    spy.assert_not_called()


def test_no_plan_reads_as_none(host):
    assert host().mda is None


def test_the_lazy_list_matches_the_eager_conversion(host):
    sequence = useq.MDASequence(
        axis_order="tpcz",
        time_plan={"interval": 0.5, "loops": 3},
        z_plan={"relative": [0, 1, 2], "go_up": True},
        channels=[{"config": "DAPI", "exposure": 10}, {"config": "FITC", "exposure": 20}],
    )
    obj = host()
    obj.mda_useq = sequence
    obj._mda = None
    assert obj.mda == useq.pycromanager.to_pycromanager(sequence)


# ------------------------------------------------------------ acquisition


def test_acquisition_hands_over_the_raw_sequence(host):
    obj = host()
    obj.mda_useq = _sequence(6)
    obj._mda = None
    with _spy() as spy:
        assert obj._mdaEventsForAcquisition() is obj.mda_useq
    spy.assert_not_called()


def test_acquisition_prefers_a_materialised_list(host):
    obj = host()
    obj.mda_useq = _sequence(6)
    explicit = [{"axes": {"time": 0}}]
    obj.mda = explicit  # setMDAparams / the constructor / a recipe load
    assert obj._mdaEventsForAcquisition() is explicit


def test_shared_data_sees_the_same_events(host, tmp_appdata):
    from glados_pycromanager.GUI.sharedFunctions import Shared_data

    sequence = _sequence(8)
    obj = host()
    obj.mda_useq = sequence
    obj._mda = None
    shared_data = Shared_data()
    with _spy() as spy:
        shared_data._mdaModeParams = obj._mdaEventsForAcquisition()
        spy.assert_not_called()
        events = shared_data._mdaModeParams
    spy.assert_called_once()
    assert events == useq.pycromanager.to_pycromanager(sequence)


@pytest.mark.parametrize("method", ["MDA_acq_from_GUI", "MDA_acq_from_Node"])
def test_both_acquire_paths_use_the_lazy_hand_over(mda_cls, method):
    source = inspect.getsource(getattr(mda_cls, method))
    assert "self.shared_data._mdaModeParams = self._mdaEventsForAcquisition()" in source
    assert "self.shared_data._mdaModeParams_useq = self.mda_useq" in source


# ------------------------------------------------------------ persistence


def test_the_backing_list_is_not_written_to_the_state_file(qapp):
    from glados_pycromanager.GUI import utils

    assert "_mda" in utils.CustomMainWindow().storingExceptions


def test_recipes_still_store_mda_and_skip_the_backing_list(qapp):
    import glados_pycromanager.GUI.nodz.nodz_main as nodz_main

    source = inspect.getsource(nodz_main)
    skip = re.search(r"mdaattr_skip = \[(.*?)\]", source).group(1)
    assert "'_mda'" in skip and "'mda_useq'" in skip
    assert "data['NODES_MDA'][node]['mda'] = nodeInst.mdaData.mda" in source
