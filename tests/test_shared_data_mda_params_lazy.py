"""Lock in the lazy `Shared_data._mdaModeParams` conversion.

Live mode (MMCORE_PLUS) assigns a raw `useq.MDASequence` to this property
instead of eagerly calling `to_pycromanager()` -- see the property docstring
in `sharedFunctions.py` and `docs/bench-live-display.md` for why (avoids a
second full pydantic-validation pass over every MDAEvent, redundant with
`core.run_mda()`'s own internal iteration). This test locks in: the getter
converts on first read, caches the result (stable `id()` across repeated
reads, and `to_pycromanager` called only once), and a plain list (the MDA
mode assignment shape) passes through untouched.
"""
from __future__ import annotations

from unittest.mock import patch

import useq
import useq.pycromanager  # noqa: F401 -- forces the submodule into sys.modules so mock.patch can target it

from glados_pycromanager.GUI.sharedFunctions import Shared_data


def test_mda_sequence_converts_lazily_and_caches(tmp_appdata):
    shared_data = Shared_data()
    sequence = useq.MDASequence(time_plan={"interval": 0.0, "loops": 5})

    with patch(
        "useq.pycromanager.to_pycromanager", wraps=useq.pycromanager.to_pycromanager
    ) as spy:
        shared_data._mdaModeParams = sequence
        spy.assert_not_called()  # assignment alone must not trigger conversion

        first = shared_data._mdaModeParams
        spy.assert_called_once()
        assert isinstance(first, list)
        assert len(first) == 5

        second = shared_data._mdaModeParams
        spy.assert_called_once()  # still just once -- second read hit the cache
        assert second is first  # same object, not just equal


def test_plain_list_passes_through_unchanged(tmp_appdata):
    shared_data = Shared_data()
    events = [{"axes": {"time": 0}}, {"axes": {"time": 1}}]
    shared_data._mdaModeParams = events
    assert shared_data._mdaModeParams is events
