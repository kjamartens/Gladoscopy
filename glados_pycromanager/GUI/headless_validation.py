"""Pure-Python validation of the headless-start dialog inputs.

The headless dialog in :mod:`glados_pycromanager.GUI.GUI_napari` collects
a Micro-Manager install path and a ``.cfg`` configuration file. Phase 10.9
introduces this small validator so the UI can gate the Start button on
real filesystem state — and so the validation logic can be tested
without instantiating Qt.
"""

from __future__ import annotations

import os


def validate_headless_inputs(
    mm_app_path: str,
    config_file: str,
) -> list[str]:
    """Return a list of validation error messages.

    An empty list means the inputs are valid. Each entry is a short
    user-facing message naming a single problem (so the dialog can show
    them as a multi-line tooltip).

    Rules:
        - ``mm_app_path`` must be a non-empty string.
        - ``mm_app_path`` must exist and be a directory.
        - ``config_file`` must be a non-empty string.
        - ``config_file`` must exist and be a regular file.
        - ``config_file`` must end with ``.cfg`` (case-insensitive).
    """
    errors: list[str] = []

    if not isinstance(mm_app_path, str) or not mm_app_path.strip():
        errors.append("Micro-Manager path is empty.")
    elif not os.path.exists(mm_app_path):
        errors.append(f"Micro-Manager path does not exist: {mm_app_path!r}")
    elif not os.path.isdir(mm_app_path):
        errors.append(f"Micro-Manager path is not a directory: {mm_app_path!r}")

    if not isinstance(config_file, str) or not config_file.strip():
        errors.append("Config file is empty.")
    elif not os.path.exists(config_file):
        errors.append(f"Config file does not exist: {config_file!r}")
    elif not os.path.isfile(config_file):
        errors.append(f"Config file is not a regular file: {config_file!r}")
    elif not config_file.lower().endswith(".cfg"):
        errors.append(f"Config file must end with '.cfg': {config_file!r}")

    return errors


def headless_inputs_are_valid(mm_app_path: str, config_file: str) -> bool:
    """Convenience boolean wrapper around :func:`validate_headless_inputs`."""
    return not validate_headless_inputs(mm_app_path, config_file)
