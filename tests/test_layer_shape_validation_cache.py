"""T-E3: the multiDstack layer-shape check runs per acquisition, not per frame.

The display path used to re-derive the acquisition plan's dimensions and walk
them against the layer's shape on *every* frame, with a `layers.pop()` plus a
zarr reset -- a full teardown and texture re-upload -- on the other side of any
mismatch. An existing layer's shape cannot drift on its own: it only stops
matching when the plan changes or the layer object is replaced, which is
exactly what the validation cache keys on.

The identity half is a weakref rather than `id(layer)` on purpose. CPython
recycles the address of a freed object, so an `id()` key can report a brand-new
layer as "already validated" -- the T-D5 bug this codebase paid for once
already.
"""
from __future__ import annotations

import gc

from glados_pycromanager.GUI.napariGlados import (
    _invalidate_layer_shape_validation,
    _layer_shape_already_validated,
    _mark_layer_shape_validated,
)


class _Layer:
    """Stand-in for a napari Image layer (only needs to be weak-referenceable)."""


class _SharedData:
    def __init__(self):
        self._mdaModeParamsGeneration = 0


def test_unvalidated_layer_reports_false():
    shared_data, layer = _SharedData(), _Layer()
    assert _layer_shape_already_validated(shared_data, 'MDA', layer) is False


def test_marked_layer_is_skipped_on_later_frames():
    shared_data, layer = _SharedData(), _Layer()
    _mark_layer_shape_validated(shared_data, 'MDA', layer)
    # Every subsequent frame of the same acquisition must short-circuit.
    for _ in range(100):
        assert _layer_shape_already_validated(shared_data, 'MDA', layer) is True


def test_new_acquisition_plan_forces_revalidation():
    shared_data, layer = _SharedData(), _Layer()
    _mark_layer_shape_validated(shared_data, 'MDA', layer)
    # The `_mdaModeParams` setter bumps this on every assignment; a different
    # plan may well have different dimensions, so the verdict must not carry.
    shared_data._mdaModeParamsGeneration += 1
    assert _layer_shape_already_validated(shared_data, 'MDA', layer) is False


def test_a_different_layer_object_is_not_validated():
    shared_data, layer = _SharedData(), _Layer()
    _mark_layer_shape_validated(shared_data, 'MDA', layer)
    assert _layer_shape_already_validated(shared_data, 'MDA', _Layer()) is False


def test_verdict_is_per_layer_name():
    shared_data, layer = _SharedData(), _Layer()
    _mark_layer_shape_validated(shared_data, 'MDA', layer)
    assert _layer_shape_already_validated(shared_data, 'OtherNode', layer) is False


def test_replacement_layer_at_a_recycled_address_is_not_validated():
    """The reason the identity key is a weakref and not `id()`."""
    shared_data = _SharedData()
    layer = _Layer()
    old_address = id(layer)
    _mark_layer_shape_validated(shared_data, 'MDA', layer)

    del layer
    gc.collect()

    # Allocate until CPython hands back the freed address (it reuses same-sized
    # objects promptly). If it never does, the test still holds -- a fresh layer
    # at a *different* address must not validate either.
    replacement = None
    for _ in range(10000):
        candidate = _Layer()
        if id(candidate) == old_address:
            replacement = candidate
            break
    if replacement is None:
        replacement = _Layer()

    assert _layer_shape_already_validated(shared_data, 'MDA', replacement) is False


def test_invalidate_drops_the_verdict():
    shared_data, layer = _SharedData(), _Layer()
    _mark_layer_shape_validated(shared_data, 'MDA', layer)
    _invalidate_layer_shape_validation(shared_data, layer_name := 'MDA')
    assert _layer_shape_already_validated(shared_data, layer_name, layer) is False


def test_invalidate_is_safe_before_anything_was_cached():
    _invalidate_layer_shape_validation(_SharedData(), 'MDA')
