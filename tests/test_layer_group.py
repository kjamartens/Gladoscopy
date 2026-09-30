"""Layer-spec normalisation, the layer group, and side-by-side placement.

The placement tests deliberately pin napari 0.7.0 semantics that the feature relies
on -- that `translate` is applied *after* `scale`, in world units -- in the same
spirit as `test_dims_batched_update.py` pinning `set_current_step`. A napari bump
that changes them should fail here loudly rather than silently mis-place a layer.
"""

import numpy as np
import pytest

from glados_pycromanager.GUI.layer_group import (
    DEFAULT_PLACEMENT_GAP_FRACTION,
    LayerSpec,
    NapariLayerGroup,
    compute_placement_offset,
    create_layer,
    normalise_layer_specs,
)


class FakeExtent:
    def __init__(self, world):
        self.world = np.asarray(world, dtype=float)


class FakeLayer:
    """Just enough of a napari layer: a world extent, a translate and a name."""

    def __init__(self, name, shape=(100, 100), scale=(1.0, 1.0), translate=(0.0, 0.0)):
        self.name = name
        self.shape = shape
        self.scale = np.asarray(scale, dtype=float)
        self.translate = np.asarray(translate, dtype=float)
        self.data = None

    @property
    def extent(self):
        #world = scale * data_extent + translate, matching napari's composition.
        mins = self.translate
        maxs = self.translate + self.scale * np.asarray(self.shape, dtype=float)
        return FakeExtent([mins, maxs])


class FakeLayerList:
    def __init__(self):
        self._layers = {}

    def __contains__(self, name):
        return name in self._layers

    def __getitem__(self, name):
        return self._layers[name]

    def remove(self, name):
        del self._layers[name]

    def add(self, layer):
        self._layers[layer.name] = layer


class FakeViewer:
    def __init__(self):
        self.layers = FakeLayerList()
        self.calls = []

    def _make(self, kind, *args, **kwargs):
        self.calls.append((kind, args, kwargs))
        layer = FakeLayer(kwargs['name'])
        layer.kwargs = kwargs
        self.layers.add(layer)
        return layer

    def add_image(self, *a, **k):
        return self._make('image', *a, **k)

    def add_points(self, *a, **k):
        return self._make('points', *a, **k)

    def add_shapes(self, *a, **k):
        return self._make('shapes', *a, **k)

    def add_labels(self, *a, **k):
        return self._make('labels', *a, **k)


# --------------------------------------------------------------------------
# normalise_layer_specs
# --------------------------------------------------------------------------

def test_legacy_tuple_is_one_spec_and_flagged_legacy():
    specs, is_legacy = normalise_layer_specs(('FFT Magnitude', 'image'))
    assert is_legacy is True
    assert [s.name for s in specs] == ['FFT Magnitude']
    assert specs[0].type == 'image'
    assert specs[0].placement == 'overlay'


def test_legacy_tuple_with_none_type_falls_back_to_shapes():
    #napariOverlay historically treated a None layerType as "give me shapes".
    specs, is_legacy = normalise_layer_specs(('thing', None))
    assert is_legacy is True
    assert specs[0].type == 'shapes'


def test_list_of_pairs_is_not_legacy():
    specs, is_legacy = normalise_layer_specs([('a', 'image'), ('b', 'points')])
    assert is_legacy is False
    assert [s.name for s in specs] == ['a', 'b']
    assert [s.type for s in specs] == ['image', 'points']


def test_single_element_list_still_opts_into_the_group_api():
    #Deliberate: `is_legacy` is not `len(specs) == 1`. A node returning a
    #one-element list gets a group, so adding a second layer later is not a
    #breaking change to its own visualise().
    specs, is_legacy = normalise_layer_specs([('only', 'image')])
    assert is_legacy is False
    assert len(specs) == 1


def test_list_of_dicts_carries_display_properties():
    specs, is_legacy = normalise_layer_specs([
        {'name': 'raw', 'type': 'image', 'colormap': 'gray'},
        {'name': 'SR', 'type': 'image', 'placement': 'right', 'scale': (0.1, 0.1)},
    ])
    assert is_legacy is False
    assert specs[0].colormap == 'gray'
    assert specs[1].placement == 'right'
    assert tuple(specs[1].scale) == (0.1, 0.1)


def test_layer_spec_instances_pass_through():
    given = [LayerSpec(name='x', type='points')]
    specs, is_legacy = normalise_layer_specs(given)
    assert specs == given
    assert is_legacy is False


def test_none_yields_no_specs():
    specs, is_legacy = normalise_layer_specs(None)
    assert specs == []
    assert is_legacy is True


def test_unknown_spec_key_is_dropped_with_a_warning(caplog):
    with caplog.at_level('WARNING'):
        specs, _ = normalise_layer_specs([{'name': 'x', 'type': 'image', 'futureKey': 1}])
    assert specs[0].name == 'x'
    assert 'futureKey' in caplog.text


def test_duplicate_layer_names_are_rejected():
    with pytest.raises(ValueError, match='duplicate'):
        normalise_layer_specs([('a', 'image'), ('a', 'points')])


def test_unknown_layer_type_is_rejected():
    with pytest.raises(ValueError, match='Unknown layer type'):
        normalise_layer_specs([('a', 'hologram')])


def test_unknown_placement_is_rejected():
    with pytest.raises(ValueError, match='Unknown placement'):
        normalise_layer_specs([{'name': 'a', 'type': 'image', 'placement': 'diagonally'}])


def test_spec_without_a_name_is_rejected():
    with pytest.raises(ValueError, match='no "name"'):
        normalise_layer_specs([{'type': 'image'}])


def test_garbage_return_value_is_rejected():
    with pytest.raises(TypeError):
        normalise_layer_specs('just a name')


# --------------------------------------------------------------------------
# create_layer
# --------------------------------------------------------------------------

def test_create_layer_seeds_only_the_types_that_need_data():
    viewer = FakeViewer()
    create_layer(viewer, LayerSpec(name='im', type='image'))
    create_layer(viewer, LayerSpec(name='pts', type='points'))
    kinds = {kind: (args, kwargs) for kind, args, kwargs in viewer.calls}
    assert len(kinds['image'][0]) == 1        # seeded with placeholder data
    assert kinds['points'][0] == ()           # created empty


def test_create_layer_passes_display_properties_through():
    viewer = FakeViewer()
    create_layer(viewer, LayerSpec(name='SR', type='image', colormap='magma',
                                   blending='additive', opacity=0.5,
                                   scale=(0.1, 0.1)))
    _, _, kwargs = viewer.calls[0]
    assert kwargs['colormap'] == 'magma'
    assert kwargs['blending'] == 'additive'
    assert kwargs['opacity'] == 0.5
    assert tuple(kwargs['scale']) == (0.1, 0.1)


def test_spec_scale_overrides_the_inherited_viewer_scale():
    viewer = FakeViewer()
    create_layer(viewer, LayerSpec(name='SR', type='image', scale=(0.1, 0.1)),
                 scale=(1.0, 1.0))
    assert tuple(viewer.calls[0][2]['scale']) == (0.1, 0.1)


def test_existing_layer_is_adopted_and_logged(caplog):
    viewer = FakeViewer()
    existing = FakeLayer('shared')
    viewer.layers.add(existing)
    with caplog.at_level('INFO'):
        got = create_layer(viewer, LayerSpec(name='shared', type='image'))
    assert got is existing
    assert viewer.calls == []
    assert 'adopting existing napari layer' in caplog.text


# --------------------------------------------------------------------------
# placement
# --------------------------------------------------------------------------

def test_overlay_placement_produces_no_offset():
    base = FakeLayer('base')
    assert compute_placement_offset(base, FakeLayer('other'), 'overlay') is None


def test_right_placement_clears_the_base_extent():
    base = FakeLayer('base', shape=(100, 100), scale=(1.0, 1.0))
    target = FakeLayer('SR', shape=(1000, 1000), scale=(0.1, 0.1))
    translate = compute_placement_offset(base, target, 'right')
    expected = 100.0 + 100.0 * DEFAULT_PLACEMENT_GAP_FRACTION
    assert translate[-1] == pytest.approx(expected)
    assert translate[-2] == pytest.approx(0.0)


def test_placement_offset_is_in_world_units_and_ignores_scale():
    """The SR layer is 10x upsampled, so its pixel count differs by 10x while its
    world extent matches. Both must take the identical offset -- this is the
    napari fact ('translate is applied after scale') the feature rests on."""
    base = FakeLayer('base', shape=(100, 100), scale=(1.0, 1.0))
    same_world_fine = FakeLayer('SR', shape=(1000, 1000), scale=(0.1, 0.1))
    same_world_coarse = FakeLayer('coarse', shape=(100, 100), scale=(1.0, 1.0))
    a = compute_placement_offset(base, same_world_fine, 'right')
    b = compute_placement_offset(base, same_world_coarse, 'right')
    assert a[-1] == pytest.approx(b[-1])


def test_below_placement_uses_the_other_axis():
    base = FakeLayer('base', shape=(100, 200), scale=(1.0, 1.0))
    target = FakeLayer('t', shape=(100, 200), scale=(1.0, 1.0))
    translate = compute_placement_offset(base, target, 'below')
    assert translate[-2] == pytest.approx(100.0 + 100.0 * DEFAULT_PLACEMENT_GAP_FRACTION)
    assert translate[-1] == pytest.approx(0.0)


def test_placement_is_idempotent():
    """Re-applying must not drift: the offset solves for where the target's world
    minimum should land, and `extent.world` already includes the current translate."""
    base = FakeLayer('base', shape=(100, 100))
    target = FakeLayer('SR', shape=(100, 100))
    first = compute_placement_offset(base, target, 'right')
    target.translate = np.asarray(first, dtype=float)
    second = compute_placement_offset(base, target, 'right')
    assert np.allclose(first, second)


def test_placement_offset_is_none_when_extents_are_unreadable():
    class NoExtent:
        translate = [0.0, 0.0]
    assert compute_placement_offset(NoExtent(), FakeLayer('t'), 'right') is None
    assert compute_placement_offset(FakeLayer('b'), NoExtent(), 'right') is None


# --------------------------------------------------------------------------
# NapariLayerGroup
# --------------------------------------------------------------------------

def _group(*names_and_placements):
    specs = [LayerSpec(name=n, type='image', placement=p) for n, p in names_and_placements]
    layers = [FakeLayer(n) for n, _ in names_and_placements]
    return NapariLayerGroup(specs=specs, layers=layers)


def test_group_is_addressed_by_name():
    group = _group(('raw', 'overlay'), ('SR', 'right'))
    assert group['raw'].name == 'raw'
    assert group['SR'].name == 'SR'
    assert group.get('nope') is None
    assert 'SR' in group
    assert len(group) == 2
    assert group.names == ['raw', 'SR']


def test_unknown_layer_name_raises_with_the_available_names():
    group = _group(('raw', 'overlay'))
    with pytest.raises(KeyError, match='raw'):
        group['typo']


def test_group_forwards_attribute_reads_and_writes_to_the_primary_layer():
    group = _group(('raw', 'overlay'), ('SR', 'right'))
    assert group.name == 'raw'
    group.data = 'written'
    assert group.layers[0].data == 'written'
    assert group.layers[1].data is None


def test_group_own_fields_are_not_forwarded():
    group = _group(('raw', 'overlay'))
    assert isinstance(group.layers, list)
    assert group.specs[0].name == 'raw'
    group.gap_fraction = 0.2
    assert group.gap_fraction == 0.2


def test_apply_placement_moves_only_non_overlay_layers():
    group = _group(('raw', 'overlay'), ('locs', 'overlay'), ('SR', 'right'))
    assert group.apply_placement() is True
    assert group['locs'].translate[-1] == pytest.approx(0.0)
    assert group['SR'].translate[-1] > 0


def test_apply_placement_skips_when_the_base_extent_has_not_moved():
    """A node rewriting layer.data every frame must not recompute placement at the
    visualisation rate."""
    group = _group(('raw', 'overlay'), ('SR', 'right'))
    assert group.apply_placement() is True
    assert group.apply_placement() is False
    assert group.apply_placement(force=True) is True


def test_apply_placement_reruns_when_the_base_extent_changes():
    group = _group(('raw', 'overlay'), ('SR', 'right'))
    group.apply_placement()
    first = float(group['SR'].translate[-1])
    group['raw'].shape = (100, 400)      # node swapped in a wider frame
    assert group.apply_placement() is True
    assert float(group['SR'].translate[-1]) > first


def test_apply_placement_against_an_external_base_layer():
    group = _group(('SR', 'right'))
    base = FakeLayer('acquisition', shape=(512, 512))
    assert group.apply_placement(base_layer=base) is True
    assert group['SR'].translate[-1] == pytest.approx(
        512.0 + 512.0 * DEFAULT_PLACEMENT_GAP_FRACTION)


def test_empty_group_places_nothing():
    group = NapariLayerGroup(specs=[], layers=[])
    assert group.apply_placement() is False
    assert group.primary is None


def test_remove_all_removes_every_layer_and_tolerates_absent_ones():
    viewer = FakeViewer()
    group = _group(('raw', 'overlay'), ('SR', 'right'))
    for layer in group.layers:
        viewer.layers.add(layer)
    viewer.layers.remove('SR')          # user already closed one
    group.remove_all(viewer)
    assert 'raw' not in viewer.layers
    assert 'SR' not in viewer.layers


# --------------------------------------------------------------------------
# Pinned napari semantics
# --------------------------------------------------------------------------

def test_translate_is_post_scale_world_units_on_real_napari_layers():
    """The one napari fact the placement feature rests on.

    On napari 0.7.0 a layer composes as `scale * data + translate`, so `translate`
    is in world units and a 10x-upsampled layer takes the same offset as the raw
    one. If a napari bump ever changes that, this fails loudly instead of silently
    stacking the SR panel on top of the image.
    """
    napari_layers = pytest.importorskip('napari.layers')
    base = napari_layers.Image(np.zeros((100, 100)), name='base', scale=(1.0, 1.0))
    sr = napari_layers.Image(np.zeros((1000, 1000)), name='SR', scale=(0.1, 0.1))

    #Same world extent despite 10x the pixels -- that is what "world units" means.
    assert base.extent.world[1][-1] == pytest.approx(sr.extent.world[1][-1], abs=1.0)

    translate = compute_placement_offset(base, sr, 'right')
    sr.translate = translate
    #The SR panel now starts to the right of where the base ends.
    assert sr.extent.world[0][-1] > base.extent.world[1][-1]
    #...and re-applying does not drift it further.
    assert np.allclose(translate, compute_placement_offset(base, sr, 'right'))


def test_translate_broadcasts_to_leading_dimensions_on_real_napari_layers():
    """`[0, offset]` must work on an n-D layer too, without padding it ourselves."""
    napari_layers = pytest.importorskip('napari.layers')
    stack = napari_layers.Image(np.zeros((5, 100, 100)), name='stack')
    stack.translate = [0.0, 42.0]
    assert list(stack.translate) == [0.0, 0.0, 42.0]
