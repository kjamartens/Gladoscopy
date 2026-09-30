"""Read-only dialog that displays a Performance Mode capture report.

Structural precedent: slack_settings_dialog.py's SlackSettingsDialog -- a
small, self-contained QDialog opened via .exec_().
"""

import logging
import os
import sys

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.observability.perf_capture import PerformanceReport, format_report_text

logger = logging.getLogger(__name__)


class PerformanceReportDialog(QDialog):
    """Shows a formatted Performance Mode report; offers "Save to file...".

    Open with `dialog.exec_()`.
    """

    def __init__(self, report: PerformanceReport, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Performance Mode report")
        self.setMinimumSize(700, 500)
        self._report_text = format_report_text(report)

        text = QPlainTextEdit(self)
        text.setReadOnly(True)
        text.setFont(QFont("Consolas", 9))
        text.setPlainText(self._report_text)

        save_btn = QPushButton("Save to file…", self)
        save_btn.clicked.connect(self._save)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        row = QHBoxLayout()
        row.addWidget(save_btn)
        row.addStretch()
        row.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addLayout(row)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Performance Mode report", "performance_report.txt", "Text files (*.txt)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self._report_text)
            logger.info("Performance Mode report saved to %s", path)
        except OSError as exc:
            logger.error("Could not save Performance Mode report to %s: %s", path, exc)
