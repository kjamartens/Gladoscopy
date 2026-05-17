"""Round-trip every `Config` dataclass field through the JSON layer.

This locks in the current schema before Phase 7 splits
`sharedFunctions.py` into `io/appdata.py`. A regression here means the
saved-state shape changed in a user-visible way.

Slack credentials live in their own focused test
(`tests/test_slack_settings_persistence.py`); this file covers all
four group dataclasses (`mda_config`, `visualisation_config`,
`micromanager_config`, `webhook_config`).
"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from glados_pycromanager.GUI.sharedFunctions import (
    Config,
    MDAConfig,
    MicroManagerConfig,
    VisualisationConfig,
    WebhookConfig,
)
from glados_pycromanager.io.appdata import (
    load_config_from_json,
    save_config_to_json,
)


def _flat_keys(cfg: Config) -> list[str]:
    """Mirror the `group.field` layout the writer uses."""
    keys: list[str] = []
    for group_field in dataclasses.fields(cfg):
        group = getattr(cfg, group_field.name)
        for f in dataclasses.fields(group):
            keys.append(f"{group_field.name}.{f.name}")
    return keys


def test_defaults_match_dataclass_defaults():
    cfg = Config()
    assert isinstance(cfg.mda_config, MDAConfig)
    assert isinstance(cfg.visualisation_config, VisualisationConfig)
    assert isinstance(cfg.micromanager_config, MicroManagerConfig)
    assert isinstance(cfg.webhook_config, WebhookConfig)


def test_all_groups_round_trip(tmp_appdata: Path):
    cfg = Config()
    # Touch every group with a value distinguishable from the default.
    cfg.mda_config.vis_method = "frameByFrame"
    cfg.mda_config.backend_method = "saved"
    cfg.mda_config.live_mode_nr_frames = 7
    cfg.visualisation_config.fps = 42
    cfg.micromanager_config.path = r"C:\some\custom\path"
    cfg.micromanager_config.config_path = r"C:\some\config.cfg"
    cfg.micromanager_config.buffer_mb = 8192
    cfg.micromanager_config.max_memory_mb = 24000
    cfg.micromanager_config.headless_backend = "Python"
    cfg.webhook_config.slack_token = "xoxb-rt"
    cfg.webhook_config.slack_secret = "sec-rt"
    cfg.webhook_config.slack_channel = "rt-channel"

    save_config_to_json(cfg)
    state_path = tmp_appdata / "Glados-PycroManager" / "glados_state.json"
    assert state_path.exists()
    payload = json.loads(state_path.read_text())
    saved = payload["GlobalData"]

    # Every flattened key landed in the JSON.
    for k in _flat_keys(cfg):
        assert k in saved, f"missing flattened key {k}"

    # And a fresh Config picks them up.
    fresh = Config()
    load_config_from_json(fresh)
    assert fresh.mda_config.vis_method == "frameByFrame"
    assert fresh.mda_config.backend_method == "saved"
    assert fresh.mda_config.live_mode_nr_frames == 7
    assert fresh.visualisation_config.fps == 42
    assert fresh.micromanager_config.path == r"C:\some\custom\path"
    assert fresh.micromanager_config.config_path == r"C:\some\config.cfg"
    assert fresh.micromanager_config.buffer_mb == 8192
    assert fresh.micromanager_config.max_memory_mb == 24000
    assert fresh.webhook_config.slack_token == "xoxb-rt"
    assert fresh.webhook_config.slack_channel == "rt-channel"


def test_load_with_no_existing_json_returns_defaults(tmp_appdata: Path):
    cfg = Config()
    out = load_config_from_json(cfg)
    # No file on disk yet — load is a no-op that returns the same cfg.
    assert out is cfg
    assert cfg.webhook_config.slack_token == ""
    assert cfg.visualisation_config.fps == 60  # baked default


def test_load_ignores_unknown_keys_and_preserves_other_top_level(tmp_appdata: Path):
    state_dir = tmp_appdata / "Glados-PycroManager"
    state_dir.mkdir()
    state_path = state_dir / "glados_state.json"
    state_path.write_text(
        json.dumps(
            {
                "GlobalData": {
                    "webhook_config.slack_token": "from-disk",
                    "webhook_config.not_a_real_field": "ignored",
                    "non_existent_group.x": "ignored",
                },
                "MDAState": {"unrelated": True},
            }
        )
    )

    cfg = Config()
    load_config_from_json(cfg)
    assert cfg.webhook_config.slack_token == "from-disk"
    # save_config_to_json must preserve unrelated top-level keys.
    save_config_to_json(cfg)
    payload = json.loads(state_path.read_text())
    assert payload.get("MDAState") == {"unrelated": True}


def test_save_overwrites_only_global_data(tmp_appdata: Path):
    state_dir = tmp_appdata / "Glados-PycroManager"
    state_dir.mkdir()
    state_path = state_dir / "glados_state.json"
    state_path.write_text(json.dumps({"OldKey": "kept", "GlobalData": {"stale": "x"}}))

    cfg = Config()
    cfg.webhook_config.slack_channel = "after-save"
    save_config_to_json(cfg)
    payload = json.loads(state_path.read_text())

    assert payload["OldKey"] == "kept"
    assert "stale" not in payload["GlobalData"]
    assert payload["GlobalData"]["webhook_config.slack_channel"] == "after-save"


@pytest.mark.parametrize(
    "group_name, field_name, sentinel",
    [
        ("mda_config", "vis_method", "frameByFrame"),
        ("mda_config", "backend_method", "saved"),
        ("mda_config", "live_mode_nr_frames", 17),
        ("visualisation_config", "fps", 24),
        ("micromanager_config", "buffer_mb", 256),
        ("micromanager_config", "max_memory_mb", 1024),
        ("webhook_config", "slack_token", "tok"),
        ("webhook_config", "slack_secret", "sec"),
        ("webhook_config", "slack_channel", "ch"),
    ],
)
def test_each_field_round_trips(tmp_appdata: Path, group_name, field_name, sentinel):
    cfg = Config()
    setattr(getattr(cfg, group_name), field_name, sentinel)
    save_config_to_json(cfg)

    fresh = Config()
    load_config_from_json(fresh)
    assert getattr(getattr(fresh, group_name), field_name) == sentinel
