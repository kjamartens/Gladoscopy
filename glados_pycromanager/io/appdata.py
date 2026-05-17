"""Read and write the per-user `glados_state.json` plus temp-folder cleanup.

Originally split across `GUI/sharedFunctions.py` (config load/save) and
`GUI/utils.py` (`storeSharedData_GlobalData`, `cleanUpTemporaryFiles`).
Phase 7.1 unifies them under `glados_pycromanager.io.appdata` with thin
re-export shims left behind for backward compatibility (Phase 7.2).

All paths route through `appdirs.user_data_dir()` so a test or sandbox
can monkeypatch a single attribute and redirect the whole tree.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import shutil
from typing import TYPE_CHECKING

import appdirs

if TYPE_CHECKING:  # avoid a runtime import cycle with sharedFunctions
    from glados_pycromanager.GUI.sharedFunctions import Config

logger = logging.getLogger(__name__)

APP_NAME = "Glados-PycroManager"
STATE_FILENAME = "glados_state.json"


def appdata_root() -> str:
    """Return `<appdirs.user_data_dir>/Glados-PycroManager`, creating it."""
    root = appdirs.user_data_dir()
    if root is None:
        raise OSError("APPDATA environment variable not found")
    target = os.path.join(root, APP_NAME)
    os.makedirs(target, exist_ok=True)
    return target


def glados_state_path() -> str:
    """Full path to the `glados_state.json` file in the per-user AppData dir."""
    return os.path.join(appdata_root(), STATE_FILENAME)


def load_config_from_json(cfg: "Config") -> "Config":
    """Overwrite `cfg` fields with values found in `glados_state.json`."""
    json_path = glados_state_path()
    if not os.path.exists(json_path):
        return cfg

    with open(json_path) as fh:
        glados_info = json.load(fh)

    saved = glados_info.get("GlobalData", {})

    # Walk every group and field, overwrite if found in JSON.
    for group_field in dataclasses.fields(cfg):
        group = getattr(cfg, group_field.name)
        for f in dataclasses.fields(group):
            key = f"{group_field.name}.{f.name}"
            if key in saved:
                try:
                    setattr(group, f.name, saved[key])
                except Exception:  # noqa: BLE001 — tolerate single-field type drift
                    pass

    return cfg


def save_config_to_json(cfg: "Config") -> None:
    """Flatten `cfg` into `{group.field: value}` and persist to AppData JSON.

    Other top-level keys already in the file (e.g. `MDA`, `MMControls`)
    are preserved untouched.
    """
    json_path = glados_state_path()

    flat: dict[str, object] = {}
    for group_field in dataclasses.fields(cfg):
        group = getattr(cfg, group_field.name)
        for f in dataclasses.fields(group):
            flat[f"{group_field.name}.{f.name}"] = getattr(group, f.name)

    existing: dict[str, object] = {}
    if os.path.exists(json_path):
        with open(json_path) as fh:
            existing = json.load(fh)

    existing["GlobalData"] = flat

    with open(json_path, "w") as fh:
        json.dump(existing, fh, indent=4)


def storeSharedData_GlobalData(shared_data) -> None:
    """Persist `shared_data.config` to the AppData JSON.

    Compatibility wrapper around `save_config_to_json` so existing
    callers keep working. The previous implementation went through
    `CustomMainWindow.save_state_globalData`, which did the same
    `Config` walk with extra `MDA` / `MMControls` key preservation —
    both are now handled in `save_config_to_json`.
    """
    save_config_to_json(shared_data.config)


def cleanUpTemporaryFiles(mainFolder: str = "./", shared_data=None) -> None:
    """Drop "ShouldBeRemoved" datasets + their on-disk folders.

    Behaviour is unchanged from the original `GUI/utils.py:61` version —
    the function exists to free up the live-acq / MDA-acq scratch
    folders that pile up in `<mainFolder>/temp/`.
    """
    logger.debug("Cleaning up temporary files")

    if shared_data is not None:
        if len(shared_data.mdaDatasets) > (3 - 1):
            for index, mdadataset in enumerate(shared_data.mdaDatasets):
                try:
                    if "ShouldBeRemoved" in mdadataset.path:
                        try:
                            shared_data.mdaDatasets.pop(index)
                        except Exception:  # noqa: BLE001
                            pass
                except Exception:  # noqa: BLE001 — JavaRAMDataStorage path absent
                    pass

    temp_dir = os.path.join(mainFolder, "temp")
    if os.path.exists(temp_dir):
        for folder in os.listdir(temp_dir):
            if "LiveAcqShouldBeRemoved" in folder or "MdaAcqShouldBeRemoved" in folder:
                full = os.path.join(temp_dir, folder)
                try:
                    shutil.rmtree(full)
                    logger.debug("Deleted %s", full)
                except Exception:  # noqa: BLE001 — file lock, permission, etc.
                    pass
