"""Stand-ins for heavy modules that import them on first real use.

``ndtiff`` imports ``dask.array`` (and with it xarray and pandas), about 1 s after napari
is loaded. Node modules and the Autonomous dock name ``ndtiff.NDTiffDataset`` only as a
*type tag*: in node metadata (read by plugin discovery at startup, to validate every
node) and in the acquisition node's port types. ``from glados_pycromanager.lazy_imports
import ndtiff`` keeps that code unchanged without importing ndtiff for it (L2.3 of
claude_launcher_project.md):

* ``ndtiff.NDTiffDataset`` is a lazy class tag. It is a ``type``, equal (``==``, ``in``)
  to itself and to the real class, ``isinstance`` / ``issubclass`` defer to the real
  class, and calling it or reading any other attribute imports ndtiff and forwards.
  While ndtiff is unimported no real NDTiffDataset can exist, so none of the
  comparisons needs the import.
* Any other attribute of ``ndtiff`` imports the module and returns the real attribute.
"""

import importlib
import sys


class _LazyClassMeta(type):
    """Metaclass of a tag standing in for class ``<_lazy_module>.<_lazy_name>``."""

    def _loaded_class(cls):
        module = sys.modules.get(cls._lazy_module)
        return getattr(module, cls._lazy_name, None) if module is not None else None

    def _real_class(cls):
        return getattr(importlib.import_module(cls._lazy_module), cls._lazy_name)

    def __eq__(cls, other):
        if other is cls:
            return True
        if isinstance(other, _LazyClassMeta):
            return (cls._lazy_module, cls._lazy_name) == (other._lazy_module, other._lazy_name)
        real = cls._loaded_class()
        return real is not None and other is real

    def __hash__(cls):
        return hash((cls._lazy_module, cls._lazy_name))

    def __instancecheck__(cls, obj):
        real = cls._loaded_class()
        return real is not None and isinstance(obj, real)

    def __subclasscheck__(cls, sub):
        if sub is cls:
            return True
        real = cls._loaded_class()
        return real is not None and issubclass(sub, real)

    def __call__(cls, *args, **kwargs):
        return cls._real_class()(*args, **kwargs)

    def __getattr__(cls, attr):
        # Only reached for attributes the tag itself lacks.
        if attr.startswith('_lazy_'):
            raise AttributeError(attr)
        return getattr(cls._real_class(), attr)

    def __repr__(cls):
        return f"<class '{cls._lazy_module}.{cls._lazy_name}'>"


def lazy_class(module: str, name: str) -> type:
    """A tag for class ``module.name``; see the module docstring."""
    tag = _LazyClassMeta(name, (), {'_lazy_module': module, '_lazy_name': name,
                                    '__module__': __name__})
    tag.__qualname__ = f'{module}_{name}'  # this module's attribute, so pickle finds it
    return tag


class LazyModule:
    """Imports module ``name`` the first time an attribute other than a tag is read."""

    __slots__ = ('_name', '_tags')

    def __init__(self, name: str, tags: dict):
        object.__setattr__(self, '_name', name)
        object.__setattr__(self, '_tags', tags)

    def __getattr__(self, attr):
        tag = self._tags.get(attr)
        if tag is not None:
            return tag
        return getattr(importlib.import_module(self._name), attr)

    def __setattr__(self, attr, value):
        raise AttributeError(f'{self!r} is read-only')

    def __repr__(self) -> str:
        return f'<lazy module {self._name!r}>'


ndtiff_NDTiffDataset = lazy_class('ndtiff', 'NDTiffDataset')
ndtiff = LazyModule('ndtiff', {'NDTiffDataset': ndtiff_NDTiffDataset})
