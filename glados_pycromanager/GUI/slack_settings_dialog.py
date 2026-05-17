"""Small QDialog that lets the user enter Slack webhook credentials at runtime.

The previous defaults baked a (now stale) token + signing secret into the
source tree — see `claude_decisions.md` (2026-05-17, "Slack credentials:
rotate-less path"). This dialog is the supported way to populate
`Shared_data.config.webhook_config` and persists via the existing
`storeSharedData_GlobalData` mechanism (`glados_state.json` in AppData).
"""

import logging
import os
import sys

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


logger = logging.getLogger(__name__)


class SlackSettingsDialog(QDialog):
    """Three line edits for Slack token, signing secret, and channel.

    Open with `dialog.exec_()`; on accept, read `.values` for the trimmed
    `(token, secret, channel)` tuple.
    """

    def __init__(self, parent=None, token: str = "", secret: str = "", channel: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Slack settings")
        self.setMinimumWidth(420)

        self._token_edit = QLineEdit(token, self)
        self._token_edit.setEchoMode(QLineEdit.Password)
        self._token_edit.setPlaceholderText("xoxb-…")

        self._secret_edit = QLineEdit(secret, self)
        self._secret_edit.setEchoMode(QLineEdit.Password)

        self._channel_edit = QLineEdit(channel, self)
        self._channel_edit.setPlaceholderText("e.g. glados-bot")

        form = QFormLayout()
        form.addRow("Slack token:", self._token_edit)
        form.addRow("Signing secret:", self._secret_edit)
        form.addRow("Channel:", self._channel_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def values(self) -> tuple[str, str, str]:
        return (
            self._token_edit.text().strip(),
            self._secret_edit.text().strip(),
            self._channel_edit.text().strip(),
        )


def apply_to_shared_data(shared_data, token: str, secret: str, channel: str) -> None:
    """Write the three Slack fields onto `shared_data.config.webhook_config`.

    Caller is responsible for persisting via `storeSharedData_GlobalData`
    once shared_data has been mutated (kept separate so unit tests can
    drive this function without touching the disk).
    """
    cfg = shared_data.config.webhook_config
    cfg.slack_token = token
    cfg.slack_secret = secret
    cfg.slack_channel = channel
    logger.info(
        "Slack settings updated (token=%s, channel=%s)",
        "set" if token else "empty",
        channel or "empty",
    )
