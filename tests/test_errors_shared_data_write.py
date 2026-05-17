"""Phase 10.4 — atomic glados_state.json write.

If ``save_config_to_json`` crashes partway through writing the JSON,
the previous version of ``glados_state.json`` must still be intact.
We test this by monkeypatching :func:`json.dump` to write some bytes
into the file handle and then raise. With the atomic-rename strategy,
the half-written content lands in ``glados_state.json.tmp`` and the
existing ``glados_state.json`` is untouched.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterator

import pytest

from glados_pycromanager.io import appdata


@dataclass
class _MiniGroup:
    name: str = "default"
    count: int = 0


@dataclass
class _MiniConfig:
    group_a: _MiniGroup = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.group_a is None:
            self.group_a = _MiniGroup()


@pytest.fixture
def isolated_appdata(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    target_dir = tmp_path / "Glados-PycroManager"
    target_dir.mkdir()
    target_file = target_dir / appdata.STATE_FILENAME
    monkeypatch.setattr(appdata, "glados_state_path", lambda: str(target_file))
    yield str(target_file)


def test_normal_save_creates_file_and_no_tmp_left_behind(
    isolated_appdata: str,
) -> None:
    cfg = _MiniConfig()
    cfg.group_a.name = "first"

    appdata.save_config_to_json(cfg)

    assert os.path.exists(isolated_appdata)
    assert not os.path.exists(isolated_appdata + ".tmp")

    with open(isolated_appdata) as fh:
        on_disk = json.load(fh)
    assert on_disk["GlobalData"]["group_a.name"] == "first"


def test_crash_mid_write_preserves_previous_file(
    isolated_appdata: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # First, lay down a "good" state file we expect to survive.
    good = _MiniConfig()
    good.group_a.name = "good-state"
    good.group_a.count = 42
    appdata.save_config_to_json(good)

    # Now monkeypatch json.dump to write half a buffer and then raise.
    real_dump = json.dump

    def half_then_die(obj, fh, *args, **kwargs):  # type: ignore[no-untyped-def]
        fh.write("{\"garbage\": \"halfway-")
        fh.flush()
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(appdata.json, "dump", half_then_die)

    new_cfg = _MiniConfig()
    new_cfg.group_a.name = "should-never-land"
    with pytest.raises(RuntimeError, match="simulated crash mid-write"):
        appdata.save_config_to_json(new_cfg)

    # The original glados_state.json is intact and still parseable.
    monkeypatch.setattr(appdata.json, "dump", real_dump)
    on_disk = real_dump and json.load(open(isolated_appdata))
    assert on_disk["GlobalData"]["group_a.name"] == "good-state"
    assert on_disk["GlobalData"]["group_a.count"] == 42

    # No leftover .tmp file (the save logic cleans it up on failure).
    assert not os.path.exists(isolated_appdata + ".tmp")


def test_save_recovers_when_existing_file_is_corrupt(
    isolated_appdata: str, caplog: pytest.LogCaptureFixture
) -> None:
    # Pre-existing corrupt file should not block a fresh save.
    with open(isolated_appdata, "w") as fh:
        fh.write("not-json-at-all{{")

    cfg = _MiniConfig()
    cfg.group_a.name = "after-corruption"
    appdata.save_config_to_json(cfg)

    with open(isolated_appdata) as fh:
        on_disk = json.load(fh)
    assert on_disk["GlobalData"]["group_a.name"] == "after-corruption"
    assert on_disk[appdata.SCHEMA_VERSION_KEY] == appdata.STATE_SCHEMA_VERSION
