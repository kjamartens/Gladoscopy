"""Phase 10.10 — defensive Slack send.

Covers :func:`glados_pycromanager.notify.slack.send_slack_message`:

- P1: a working mock client receives the call and the helper returns True.
- N1: an empty token causes the helper to log info and return False
  without raising.
- N2: no client configured: same skip path.
- N3: when the client raises, the helper wraps it in BackendError.
"""

from __future__ import annotations

import logging
import types

import pytest

from glados_pycromanager.errors import BackendError
from glados_pycromanager.notify import slack


def _make_cfg(*, token: str = "xoxb-test", client: object | None = None,
              channel: str = "#general") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        slack_token=token,
        slack_channel=channel,
        slack_client=client,
    )


def test_happy_path_calls_client_and_returns_true() -> None:
    seen: dict = {}

    class _Client:
        def chat_postMessage(self, channel: str, text: str) -> None:
            seen["channel"] = channel
            seen["text"] = text

    cfg = _make_cfg(client=_Client(), channel="#lab")
    assert slack.send_slack_message(cfg, "hello") is True
    assert seen == {"channel": "#lab", "text": "hello"}


def test_empty_token_no_ops_with_info_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cfg = _make_cfg(token="")
    with caplog.at_level(logging.INFO, logger=slack.logger.name):
        result = slack.send_slack_message(cfg, "anything")
    assert result is False
    assert any("Slack send skipped" in rec.message for rec in caplog.records)


def test_whitespace_token_is_treated_as_empty() -> None:
    cfg = _make_cfg(token="    ")
    assert slack.send_slack_message(cfg, "anything") is False


def test_no_client_is_skipped_even_if_token_present() -> None:
    cfg = _make_cfg(token="xoxb-real", client=None)
    assert slack.send_slack_message(cfg, "anything") is False


def test_none_cfg_is_skipped() -> None:
    assert slack.send_slack_message(None, "anything") is False


def test_client_raise_is_wrapped_as_backend_error() -> None:
    class _Boomer:
        def chat_postMessage(self, channel: str, text: str) -> None:
            raise RuntimeError("network down")

    cfg = _make_cfg(client=_Boomer())
    with pytest.raises(BackendError, match="Slack send"):
        slack.send_slack_message(cfg, "hi")


def test_client_raise_preserves_cause() -> None:
    class _SlackApiError(Exception):
        pass

    class _Boomer:
        def chat_postMessage(self, channel: str, text: str) -> None:
            raise _SlackApiError("invalid_auth")

    cfg = _make_cfg(client=_Boomer())
    try:
        slack.send_slack_message(cfg, "hi")
    except BackendError as final:
        assert isinstance(final.__cause__, _SlackApiError)
    else:  # pragma: no cover
        pytest.fail("BackendError not raised")


def test_slack_is_configured_paths() -> None:
    assert slack.slack_is_configured(None) is False
    assert slack.slack_is_configured(_make_cfg(token="")) is False
    assert slack.slack_is_configured(_make_cfg(token="x", client=None)) is False
    assert slack.slack_is_configured(_make_cfg(token="x", client=object())) is True
