"""
glados_pycromanager package initialization file.
"""


def load_appdata_plugins() -> None:
    """Trigger the deferred AppData drop-in walk for all node subpackages.

    Must be called exactly once, when the autonomous-microscopy dock is
    first constructed. Idempotent — safe to call multiple times.
    """
    from glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements import _load_appdata as _am
    from glados_pycromanager.AutonomousMicroscopy.CustomFunctions import _load_appdata as _cf
    from glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis import _load_appdata as _rt
    _am()
    _cf()
    _rt()
