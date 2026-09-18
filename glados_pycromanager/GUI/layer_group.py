"""Multi-layer visualisation support for real-time-analysis nodes.

An RT-analysis node declares the napari layers it wants from `visualise_init()`.
Historically that was exactly one layer, returned as a `(name, type)` 2-tuple, and
`visualise(image, metadata, core, napariLayer, ...)` received that single
`napari.layers.Layer`. A node that wants several layers -- say a super-resolution
render beside the raw frame it was reconstructed from -- had no way to ask for them.

This module adds the declaration format and the group object, without changing what
a single-layer node sees:

- `normalise_layer_specs()` accepts the legacy 2-tuple, a list of 2-tuples, a list of
  dicts, or a list of `LayerSpec`, and reports whether the node used the legacy form.
- A **legacy** declaration keeps receiving the bare napari layer in `visualise()`.
  That is the load-bearing back-compat rule: every shipped node is untouched, and a
  group object only ever reaches a node that opted in by returning a list.
- `NapariLayerGroup` is the mapping-by-name that an opted-in node receives instead.

It also owns side-by-side placement. napari's grid mode is a global, all-or-nothing
viewer setting, so it cannot express "these three layers overlaid, that one beside
them". Offsetting a layer's `translate` can, and the node stays layout-free: it
declares `placement='right'` and the backend computes the offset.

Kept free of Qt and of napari imports (it only ever *uses* objects handed to it), so
it is unit-testable headlessly against fakes -- same posture as `frame_ring.py` and
`frame_writer.py`.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

#: Gap between side-by-side panels, as a fraction of the base layer's world extent.
#: Purely cosmetic -- enough that the two panels read as separate without wasting
#: canvas.
DEFAULT_PLACEMENT_GAP_FRACTION = 0.05

#: Layer types `visualise_init()` may ask for, mapped to the viewer factory that
#: builds them. Mirrors the ladder that used to live inline in `napariOverlay`.
LAYER_FACTORIES = {
    'image': 'add_image',
    'labels': 'add_labels',
    'points': 'add_points',
    'shapes': 'add_shapes',
    'surface': 'add_surface',
    'tracks': 'add_tracks',
    'vectors': 'add_vectors',
}

#: Layer types whose napari factory requires positional data; the others are happy
#: being created empty and filled by the node's first `visualise()` call.
_NEEDS_SEED_DATA = ('image', 'labels', 'surface', 'tracks')

PLACEMENTS = ('overlay', 'right', 'below')


@dataclass(frozen=True)
class LayerSpec:
    """One napari layer an RT-analysis node asked for."""

    name: str
    type: str = 'image'
    colormap: str | None = None
    blending: str | None = None
    opacity: float | None = None
    visible: bool = True
    placement: str = 'overlay'
    scale: Sequence[float] | None = None

    def __post_init__(self):
        if self.type not in LAYER_FACTORIES:
            raise ValueError(
                f"Unknown layer type {self.type!r} for layer {self.name!r}; "
                f"expected one of {sorted(LAYER_FACTORIES)}")
        if self.placement not in PLACEMENTS:
            raise ValueError(
                f"Unknown placement {self.placement!r} for layer {self.name!r}; "
                f"expected one of {PLACEMENTS}")


def _spec_from_mapping(entry):
    """A dict spec. `name` is required; everything else falls back to the defaults."""
    unknown = set(entry) - {f.name for f in LayerSpec.__dataclass_fields__.values()}
    if unknown:
        # Not fatal: a node written against a later Glados may declare keys this
        # version does not know. Drop them loudly rather than refusing the layer.
        logging.warning('Ignoring unknown layer-spec key(s) %s for layer %r',
                        sorted(unknown), entry.get('name'))
        entry = {k: v for k, v in entry.items() if k not in unknown}
    if 'name' not in entry:
        raise ValueError(f'Layer spec {entry!r} has no "name"')
    return LayerSpec(**entry)


def _spec_from_pair(entry):
    """The `(name, type)` form, in either the legacy top-level or list position."""
    name, layer_type = entry
    #A node may return `(name, None)` -- `napariOverlay` historically treated a
    #None layerType as "give me a shapes layer".
    return LayerSpec(name=name, type=layer_type if layer_type is not None else 'shapes')


def normalise_layer_specs(result) -> tuple[list[LayerSpec], bool]:
    """Normalise a `visualise_init()` return value into layer specs.

    Returns `(specs, is_legacy)`. `is_legacy` is True only for the historical
    `(name, type)` 2-tuple, and is what decides whether the node's `visualise()`
    receives a bare napari layer (legacy) or a `NapariLayerGroup` (opted in). It is
    deliberately *not* `len(specs) == 1`: a node that returns a one-element list has
    opted into the group API and should get a group, so that adding a second layer
    later is not a breaking change to its own `visualise()`.
    """
    if result is None:
        return [], True

    #Legacy: a bare (name, type) pair. Distinguished from a list of specs by being a
    #tuple of exactly two non-collection items.
    if (isinstance(result, tuple) and len(result) == 2
            and not isinstance(result[0], (list, tuple, dict, LayerSpec))):
        return [_spec_from_pair(result)], True

    if isinstance(result, (str, bytes)) or not isinstance(result, Sequence):
        raise TypeError(
            f'visualise_init() returned {type(result).__name__}; expected a '
            '(name, type) tuple or a list of layer specs')

    specs = []
    for entry in result:
        if isinstance(entry, LayerSpec):
            specs.append(entry)
        elif isinstance(entry, dict):
            specs.append(_spec_from_mapping(entry))
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            specs.append(_spec_from_pair(entry))
        else:
            raise TypeError(
                f'Unsupported layer spec {entry!r}; expected a LayerSpec, a dict, '
                'or a (name, type) pair')

    names = [s.name for s in specs]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(f'visualise_init() declared duplicate layer name(s): {sorted(duplicates)}')

    return specs, False


def create_layer(viewer, spec: LayerSpec, scale=None, seed_data=None):
    """Create (or adopt) the napari layer described by `spec`.

    Adopting an existing layer of the same name is long-standing `napariOverlay`
    behaviour and is kept, but it is logged: with several layers per node, silently
    sharing another node's layer is a plausible failure mode rather than a
    theoretical one.
    """
    if spec.name in viewer.layers:
        logging.info('RT visualisation: adopting existing napari layer %r rather than '
                     'creating one; another node may already own it', spec.name)
        return viewer.layers[spec.name]

    kwargs = {'name': spec.name}
    layer_scale = spec.scale if spec.scale is not None else scale
    if layer_scale is not None:
        kwargs['scale'] = layer_scale
    if spec.colormap is not None:
        kwargs['colormap'] = spec.colormap
    if spec.blending is not None:
        kwargs['blending'] = spec.blending
    if spec.opacity is not None:
        kwargs['opacity'] = spec.opacity
    if not spec.visible:
        kwargs['visible'] = spec.visible

    factory = getattr(viewer, LAYER_FACTORIES[spec.type])
    if spec.type in _NEEDS_SEED_DATA:
        data = seed_data if seed_data is not None else _default_seed(spec.type)
        return factory(data, **kwargs)
    return factory(**kwargs)


def _default_seed(layer_type):
    """Placeholder data for the layer types whose factory demands some."""
    import numpy as np
    if layer_type in ('image', 'labels'):
        #Matches the historical `np.zeros((32,32))` placeholder; the node's first
        #visualise() replaces it.
        return np.zeros((32, 32), dtype=np.uint8 if layer_type == 'labels' else float)
    return []


def _world_extent(layer):
    """`(min, max)` of the layer's world extent along every axis, or None."""
    try:
        extent = layer.extent.world
    except (AttributeError, TypeError, ValueError):
        return None
    try:
        return extent[0], extent[1]
    except (IndexError, TypeError):
        return None


def compute_placement_offset(base_layer, target_layer, placement,
                             gap_fraction=DEFAULT_PLACEMENT_GAP_FRACTION):
    """The `translate` value that puts `target_layer` beside `base_layer`.

    Works in **world** units. On napari 0.7.0 a layer's transform composes as
    `scale * data + translate`, so `translate` is applied *after* `scale` -- which is
    why a 10x-upsampled super-resolution layer (whose `scale` is a tenth of the raw
    layer's) takes exactly the same offset as any other layer, and why the offset
    must not be computed in pixels.

    Returns the full translate sequence to assign, or None when the extents cannot
    be read (a layer still being constructed). Idempotent: it solves for where the
    target's world minimum should land, so re-applying it does not drift.
    """
    if placement == 'overlay':
        return None
    axis = -1 if placement == 'right' else -2

    base = _world_extent(base_layer)
    target = _world_extent(target_layer)
    if base is None or target is None:
        return None

    try:
        span = float(base[1][axis]) - float(base[0][axis])
        desired_min = float(base[1][axis]) + span * gap_fraction
        current_min = float(target[0][axis])
    except (IndexError, TypeError, ValueError):
        return None

    #`or []` would be ambiguous here: napari hands back an ndarray, whose truth
    #value raises. Convert explicitly and fall back on the extent's dimensionality.
    current = getattr(target_layer, 'translate', None)
    translate = [float(v) for v in current] if current is not None else []
    if not translate:
        translate = [0.0] * len(target[0])
    #`extent.world` and `translate` are both ordered with the displayed axes last,
    #so a negative index addresses the same axis in either.
    translate[axis] = float(translate[axis]) + (desired_min - current_min)
    return translate


@dataclass
class NapariLayerGroup:
    """The napari layers one RT-analysis node owns, addressed by name.

    Handed to an opted-in node's `visualise()` in place of a single layer:

        def visualise(self, image, metadata, core, napariLayer, **kwargs):
            napariLayer['Demo: peaks'].data = self.peaks

    Attribute access falls through to the primary (first-declared) layer. That is
    belt-and-braces rather than a compatibility mechanism -- a group only ever
    reaches code that asked for one -- but it keeps generic helpers that do
    `layer.data = x` or read `.name` working.
    """

    specs: list[LayerSpec]
    layers: list[Any] = field(default_factory=list)
    gap_fraction: float = DEFAULT_PLACEMENT_GAP_FRACTION
    _placed_extent: Any = field(default=None, repr=False)

    #Attributes that belong to the group itself and must never be forwarded to the
    #primary layer. Built from the dataclass fields so it cannot drift.
    _OWN = frozenset({'specs', 'layers', 'gap_fraction', '_placed_extent'})

    @property
    def names(self) -> list[str]:
        return [spec.name for spec in self.specs]

    @property
    def primary(self):
        return self.layers[0] if self.layers else None

    def __getitem__(self, name):
        for spec, layer in zip(self.specs, self.layers):
            if spec.name == name:
                return layer
        raise KeyError(f'{name!r} is not one of this node\'s layers: {self.names}')

    def get(self, name, default=None):
        try:
            return self[name]
        except KeyError:
            return default

    def spec_for(self, name) -> LayerSpec:
        for spec in self.specs:
            if spec.name == name:
                return spec
        raise KeyError(f'{name!r} is not one of this node\'s layers: {self.names}')

    def __contains__(self, name):
        return name in self.names

    def __iter__(self):
        return iter(self.layers)

    def __len__(self):
        return len(self.layers)

    def __getattr__(self, item):
        #Only reached for attributes the group itself does not define.
        if item.startswith('_') or item in NapariLayerGroup._OWN:
            raise AttributeError(item)
        layers = self.__dict__.get('layers') or []
        if not layers:
            raise AttributeError(item)
        return getattr(layers[0], item)

    def __setattr__(self, item, value):
        if item in NapariLayerGroup._OWN or item.startswith('_'):
            object.__setattr__(self, item, value)
            return
        layers = self.__dict__.get('layers') or []
        #Probe the instance, not the type: a napari layer exposes `data` as a class
        #property, but anything setting its attributes in __init__ would not be
        #matched by a type-level check.
        if layers and hasattr(layers[0], item):
            setattr(layers[0], item, value)
            return
        object.__setattr__(self, item, value)

    def apply_placement(self, base_layer=None, force=False):
        """Offset every non-overlay layer so it sits beside `base_layer`.

        `base_layer` defaults to the group's own primary layer. Re-applying is cheap
        and safe; it is skipped entirely when the base extent has not moved, since a
        node that rewrites `layer.data` every frame would otherwise recompute this
        at the visualisation rate.
        """
        base = base_layer if base_layer is not None else self.primary
        if base is None:
            return False

        extent = _world_extent(base)
        if extent is None:
            return False
        marker = (tuple(float(v) for v in extent[0]), tuple(float(v) for v in extent[1]))
        if not force and marker == self._placed_extent:
            return False

        moved = False
        for spec, layer in zip(self.specs, self.layers):
            if spec.placement == 'overlay' or layer is base:
                continue
            translate = compute_placement_offset(base, layer, spec.placement,
                                                 self.gap_fraction)
            if translate is None:
                continue
            try:
                layer.translate = translate
                moved = True
            except (AttributeError, ValueError) as exc:
                logging.debug('Could not place layer %r: %s', spec.name, exc)
        self._placed_extent = marker
        return moved

    def remove_all(self, viewer):
        """Remove every layer of this group from the viewer, ignoring absent ones."""
        for name in self.names:
            try:
                if name in viewer.layers:
                    viewer.layers.remove(name)
            except (KeyError, ValueError) as exc:
                logging.debug('Could not remove layer %r: %s', name, exc)
