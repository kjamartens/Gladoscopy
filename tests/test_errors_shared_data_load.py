"""Phase 10.3 — validate glados_state.json on load.

Covers the boundary check in
``glados_pycromanager.io.appdata.load_config_from_json``:

* P1: a freshly saved state file round-trips through ``save``/``load``.
* N1: a syntactically broken JSON file raises :class:`ConfigError`.
* N2: under ``strict=True``, a file without a ``schema_version`` key
  raises :class:`ConfigError`; the default (legacy mode) accepts it
  with a warning.
* N3: a file with ``schema_version`` greater than the current build's
  supports raises :class:`ConfigError`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Iterator

import pytest

from glados_pycromanager.errors import ConfigError
from glados_pycromanager.io import appdata


@dataclass
class _MiniGroup:
    name: str = "default"
    count: int = 0


@dataclass
class _MiniConfig:
    """Stand-in for `Shared_data.config` — minimal dataclass-of-dataclasses."""

    group_a: _MiniGroup = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.group_a is None:
            self.group_a = _MiniGroup()


@pytest.fixture
def isolated_appdata(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Redirect appdata.glados_state_path() to a per-test directory."""
    target_dir = tmp_path / "Glados-PycroManager"
    target_dir.mkdir()
    target_file = target_dir / appdata.STATE_FILENAME
    monkeypatch.setattr(appdata, "glados_state_path", lambda: str(target_file))
    yield str(target_file)


def test_round_trip_writes_and_loads_with_schema_version(
    isolated_appdata: str,
) -> None:
    cfg = _MiniConfig()
    cfg.group_a.name = "after-edit"
    cfg.group_a.count = 7

    appdata.save_config_to_json(cfg)

    with open(isolated_appdata) as fh:
        on_disk = json.load(fh)
    assert on_disk[appdata.SCHEMA_VERSION_KEY] == appdata.STATE_SCHEMA_VERSION
    assert on_disk["GlobalData"]["group_a.name"] == "after-edit"
    assert on_disk["GlobalData"]["group_a.count"] == 7

    reloaded = appdata.load_config_from_json(_MiniConfig())
    assert reloaded.group_a.name == "after-edit"
    assert reloaded.group_a.count == 7


def test_corrupted_json_raises_config_error(
    isolated_appdata: str,
) -> None:
    with open(isolated_appdata, "w") as fh:
        fh.write("{not-json,,,")

    with pytest.raises(ConfigError) as info:
        appdata.load_config_from_json(_MiniConfig())
    assert "unreadable" in str(info.value)


def test_missing_version_is_accepted_in_legacy_mode(
    isolated_appdata: str, caplog: pytest.LogCaptureFixture
) -> None:
    with open(isolated_appdata, "w") as fh:
        json.dump({"GlobalData": {"group_a.name": "from-legacy"}}, fh)

    with caplog.at_level(logging.WARNING, logger=appdata.logger.name):
        cfg = appdata.load_config_from_json(_MiniConfig())
    assert cfg.group_a.name == "from-legacy"
    assert any(
        "no 'schema_version'" in rec.message
        or "no schema_version" in rec.message
        for rec in caplog.records
    )


def test_missing_version_raises_in_strict_mode(
    isolated_appdata: str,
) -> None:
    with open(isolated_appdata, "w") as fh:
        json.dump({"GlobalData": {"group_a.name": "x"}}, fh)

    with pytest.raises(ConfigError) as info:
        appdata.load_config_from_json(_MiniConfig(), strict=True)
    assert appdata.SCHEMA_VERSION_KEY in str(info.value)


def test_future_version_raises(isolated_appdata: str) -> None:
    with open(isolated_appdata, "w") as fh:
        json.dump(
            {
                appdata.SCHEMA_VERSION_KEY: appdata.STATE_SCHEMA_VERSION + 7,
                "GlobalData": {},
            },
            fh,
        )

    with pytest.raises(ConfigError) as info:
        appdata.load_config_from_json(_MiniConfig())
    assert "unsupported" in str(info.value)


def test_non_object_root_raises(isolated_appdata: str) -> None:
    with open(isolated_appdata, "w") as fh:
        json.dump([1, 2, 3], fh)

    with pytest.raises(ConfigError):
        appdata.load_config_from_json(_MiniConfig())


def test_globaldata_non_dict_raises(isolated_appdata: str) -> None:
    with open(isolated_appdata, "w") as fh:
        json.dump(
            {
                appdata.SCHEMA_VERSION_KEY: appdata.STATE_SCHEMA_VERSION,
                "GlobalData": "oops",
            },
            fh,
        )

    with pytest.raises(ConfigError):
        appdata.load_config_from_json(_MiniConfig())


def test_missing_file_returns_unmodified(isolated_appdata: str) -> None:
    # No file at all — load should leave the passed-in cfg untouched.
    assert not os.path.exists(isolated_appdata)
    cfg = _MiniConfig()
    cfg.group_a.name = "fresh"
    result = appdata.load_config_from_json(cfg)
    assert result is cfg
    assert result.group_a.name == "fresh"
