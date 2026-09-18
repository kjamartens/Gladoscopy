"""`metadata_refactor` rebuilds Axes once per frame, not once per caller.

On MMCORE_PLUS the frame-ring consumer thread refactors a frame's metadata
before handing it on, and the multiDstack display branch then refactored the
same dict again on the **GUI thread**. The second call cannot simply be deleted:
the pycromanager backends queue raw metadata straight from their acquisition
callback (`grab_image_liveVisualisation_and_liveAnalysis`), so there the
display-side call is the only one there is.

Marking the dict is what lets both callers stay while only one does the work.
It survives the hand-off because the function mutates its argument in place and
returns it -- the same property `napariGlados.ZARR_WRITTEN_SLICE_KEY` relies on.
"""
from __future__ import annotations

import collections

from glados_pycromanager.GUI.utils import METADATA_REFACTORED_KEY, metadata_refactor


class _Event:
    """Stands in for a useq MDAEvent: only `.index` is read."""

    def __init__(self, index, on_access=None):
        self._index = index
        self._on_access = on_access

    @property
    def index(self):
        if self._on_access is not None:
            self._on_access()
        return self._index


def test_axes_are_remapped_to_the_long_names():
    metadata = {'mda_event': _Event({'t': 4, 'c': 1, 'Z': 2, 'p': 0})}
    out = metadata_refactor(metadata)
    assert out['Axes'] == {'time': 4, 'channel': 1, 'z': 2, 'position': 0}
    assert isinstance(out['Axes'], collections.OrderedDict)


def test_the_second_call_does_no_work():
    calls = []
    metadata = {'mda_event': _Event({'t': 7}, on_access=lambda: calls.append(1))}
    metadata_refactor(metadata)
    assert len(calls) == 1
    metadata_refactor(metadata)
    metadata_refactor(metadata)
    assert len(calls) == 1, 'Axes were rebuilt again for an already-refactored frame'


def test_the_result_is_unchanged_by_the_repeat():
    metadata = {'mda_event': _Event({'t': 4, 'Z': 2})}
    first = dict(metadata_refactor(metadata)['Axes'])
    assert metadata_refactor(metadata)['Axes'] == first


def test_the_mark_travels_with_the_dict():
    """It is the same object, mutated in place -- that is what makes this work."""
    metadata = {'mda_event': _Event({'t': 1})}
    out = metadata_refactor(metadata)
    assert out is metadata
    assert metadata[METADATA_REFACTORED_KEY] is True


def test_a_frame_with_no_mda_event_is_untouched():
    """The live-sequence path synthesises its own Axes and has no mda_event."""
    metadata = {'Axes': {'time': 3}}
    out = metadata_refactor(metadata)
    assert out['Axes'] == {'time': 3}
    assert METADATA_REFACTORED_KEY not in out


def test_a_fresh_frame_is_still_refactored_after_an_earlier_one_was():
    """The mark is per-dict, not global state."""
    first = {'mda_event': _Event({'t': 0})}
    metadata_refactor(first)
    second = {'mda_event': _Event({'t': 1})}
    assert metadata_refactor(second)['Axes'] == {'time': 1}
