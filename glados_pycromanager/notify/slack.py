"""Defensive Slack send helper (Phase 10.10).

Wraps :meth:`slack.WebClient.chat_postMessage` (slack-sdk legacy
import path used elsewhere in the project) so that:

* an unconfigured install (empty token, missing client) **no-ops**
  with a single ``logging.info`` line instead of raising;
* any network / API failure raises
  :class:`~glados_pycromanager.errors.BackendError` with the original
  exception chained via ``__cause__``.

Callers pass the live :class:`WebhookConfig`-like dataclass and the
text; this module does not touch ``Shared_data`` directly so it is
trivially testable.
"""

from __future__ import annotations

import logging
from typing import Any

from glados_pycromanager.errors import BackendError

logger = logging.getLogger(__name__)


def slack_is_configured(webhook_cfg: Any) -> bool:
    """Return True iff a Slack send would have a token and a client."""
    if webhook_cfg is None:
        return False
    token = getattr(webhook_cfg, "slack_token", "") or ""
    if not token.strip():
        return False
    if getattr(webhook_cfg, "slack_client", None) is None:
        return False
    return True


def send_slack_message(webhook_cfg: Any, text: str) -> bool:
    """Attempt to post ``text`` to the configured Slack channel.

    Args:
        webhook_cfg: A ``WebhookConfig``-like object with at least
            ``slack_token`` (str), ``slack_channel`` (str), and
            ``slack_client`` (an object exposing ``chat_postMessage``).
        text: The message body.

    Returns:
        ``True`` when the post call succeeded, ``False`` when the
        send was skipped because Slack is not configured (no token /
        no client).

    Raises:
        BackendError: If the send is attempted and the underlying
            client raises. The original exception is preserved as
            ``__cause__``.
    """
    if not slack_is_configured(webhook_cfg):
        logger.info(
            "Slack send skipped: no Slack token / client (configure via "
            "'Slack settings…')"
        )
        return False

    client = webhook_cfg.slack_client
    channel = getattr(webhook_cfg, "slack_channel", "")
    try:
        client.chat_postMessage(channel=channel, text=text)
    except Exception as exc:  # noqa: BLE001 — re-raised as typed
        raise BackendError(
            f"Slack send to {channel!r} failed: {exc}"
        ) from exc
    return True
