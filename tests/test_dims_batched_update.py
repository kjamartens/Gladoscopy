"""T-E1: dimension steps are set in one update, not one per dimension.

`Dims.set_current_step(axis, value)` with scalars assigns napari's `point`
field once per call, and every assignment emits a `point` event that forces a
complete re-slice: zarr chunk fetch, decompress, contrast rescan, GPU upload.
The multiDstack display path called it once per dimension per displayed frame,
so a 4-D acquisition paid four full re-slices to show one frame.

The same method accepts sequences, and that form routes through a single
`set_point`, which builds the whole tuple and assigns `point` once. These tests
are the measurement the task asked for rather than an assumption about the API,
so they assert on the event count against the pinned napari, and will fail
loudly if a future napari stops coalescing.
"""
from __future__ import annotations

import pytest

from napari.components.dims import Dims


def _dims(ndim):
    return Dims(ndim=ndim, range=[(0, 10, 1)] * ndim)


def _count_point_events(dims, call):
    events = []
    dims.events.point.connect(lambda event: events.append(event))
    call(dims)
    return len(events)


@pytest.mark.parametrize("ndim", [2, 3, 4])
def test_the_batched_form_emits_one_event_regardless_of_ndim(ndim):
    steps = list(range(1, ndim + 1))

    count = _count_point_events(
        _dims(ndim),
        lambda d: d.set_current_step(list(range(ndim)), steps),
    )

    assert count == 1


@pytest.mark.parametrize("ndim", [2, 3, 4])
def test_the_per_axis_loop_emits_one_event_per_dimension(ndim):
    """The behaviour being replaced -- pinned so the win is not silently lost."""
    steps = list(range(1, ndim + 1))

    count = _count_point_events(
        _dims(ndim),
        lambda d: [d.set_current_step(ax, v) for ax, v in enumerate(steps)],
    )

    assert count == ndim


def test_both_forms_land_on_the_same_step():
    """Coalescing must not change where the sliders end up."""
    steps = [1, 2, 3, 4]

    per_axis = _dims(4)
    for axis, value in enumerate(steps):
        per_axis.set_current_step(axis, value)

    batched = _dims(4)
    batched.set_current_step(list(range(4)), steps)

    assert batched.current_step == per_axis.current_step == tuple(steps)


def test_an_empty_batch_is_a_no_op():
    """A zero-dimension acquisition must not raise on the sequence form."""
    dims = _dims(2)

    dims.set_current_step([], [])

    assert dims.current_step == (0, 0)
