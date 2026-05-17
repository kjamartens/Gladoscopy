"""Round-trip test for Slack credentials through the Shared_data JSON layer.

These exercise the same path the UI takes when the user enters values in
the SlackSettingsDialog (Phase 2.2/2.3): mutate
`config.webhook_config`, persist via `save_config_to_json` (the function
`storeSharedData_GlobalData` ultimately wraps), then read back via
`load_config_from_json` on a fresh Config.
"""
import json
import os
from types import SimpleNamespace

import pytest

from glados_pycromanager.GUI.sharedFunctions import (
    Config,
    load_config_from_json,
    save_config_to_json,
)
from glados_pycromanager.GUI.slack_settings_dialog import apply_to_shared_data


@pytest.fixture
def fake_appdata(tmp_path, monkeypatch):
    """Redirect appdirs.user_data_dir to a tmp dir for both modules."""
    target = tmp_path / "appdata"
    target.mkdir()
    monkeypatch.setattr(
        "glados_pycromanager.GUI.sharedFunctions.appdirs.user_data_dir",
        lambda *a, **kw: str(target),
    )
    return target


def test_apply_to_shared_data_writes_three_fields():
    cfg = Config()
    shared = SimpleNamespace(config=cfg)

    apply_to_shared_data(shared, "xoxb-fake", "secret-fake", "channel-fake")

    assert cfg.webhook_config.slack_token == "xoxb-fake"
    assert cfg.webhook_config.slack_secret == "secret-fake"
    assert cfg.webhook_config.slack_channel == "channel-fake"


def test_apply_then_save_then_load_round_trips(fake_appdata):
    cfg = Config()
    shared = SimpleNamespace(config=cfg)

    apply_to_shared_data(shared, "xoxb-abc", "sig-xyz", "glados-bot-test")
    save_config_to_json(cfg)

    # JSON exists in the redirected appdata.
    state_path = os.path.join(str(fake_appdata), "Glados-PycroManager", "glados_state.json")
    assert os.path.exists(state_path)
    with open(state_path) as fh:
        payload = json.load(fh)
    assert payload["GlobalData"]["webhook_config.slack_token"] == "xoxb-abc"
    assert payload["GlobalData"]["webhook_config.slack_secret"] == "sig-xyz"
    assert payload["GlobalData"]["webhook_config.slack_channel"] == "glados-bot-test"

    # Fresh Config picks up the same values on load.
    fresh = Config()
    assert fresh.webhook_config.slack_token == ""
    load_config_from_json(fresh)
    assert fresh.webhook_config.slack_token == "xoxb-abc"
    assert fresh.webhook_config.slack_secret == "sig-xyz"
    assert fresh.webhook_config.slack_channel == "glados-bot-test"


def test_defaults_are_empty_strings():
    cfg = Config()
    assert cfg.webhook_config.slack_token == ""
    assert cfg.webhook_config.slack_secret == ""
    assert cfg.webhook_config.slack_channel == ""
