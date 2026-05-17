"""Plugin-discovery utilities.

Per ADR 0002, autonomous-microscopy nodes can be added either by
shipping a `.py` in the source tree or by dropping one into the
per-user AppData folder. This package provides the single, testable
loader the three `AutonomousMicroscopy/*/__init__.py` files now call.
"""

from glados_pycromanager.plugins.discovery import (  # noqa: F401
    load_node_modules,
    user_appdata_dir_for,
)
