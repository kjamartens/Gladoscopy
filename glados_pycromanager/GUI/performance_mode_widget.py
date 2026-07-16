"""Performance Mode: a Start/Stop toggle panel that records CPU/memory/
thread/hotspot data for a short capture window, then shows a report.

Built on top of glados_pycromanager/observability/perf_capture.py (shared
with the dev-only --profile-runtime CLI flag in GUI_napari.py) plus the
Performance Mode subprocess IPC added to AnalysisClass.py's
AnalysisProcess_customFunction (start_profiling/stop_profiling).
"""

import logging
import os
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.GUI.AnalysisClass import AnalysisProcess_customFunction
from glados_pycromanager.GUI.performance_report_dialog import PerformanceReportDialog
from glados_pycromanager.observability.perf_capture import PerformanceCapture

logger = logging.getLogger(__name__)


class PerformanceModeWidget(QWidget):
    """Content widget for the "Performance" dock panel.

    Takes `shared_data` directly so it can be embedded from either entry
    point: _dock_widget.py's GladosWidget-based MainWidget (napari-plugin
    path) or napariGlados.py's dockWidgets-based standalone path.
    """

    def __init__(self, shared_data):
        super().__init__()
        self.shared_data = shared_data
        self._capture = None
        self._running = False

        self._spinbox = QSpinBox(self)
        self._spinbox.setRange(1, 120)
        self._spinbox.setValue(self.shared_data.config.performance_config.default_capture_seconds)
        self._spinbox.setSuffix(" s")

        self._button = QPushButton("Start Performance Mode", self)
        self._button.clicked.connect(self._on_button_clicked)

        self._status_label = QLabel("Idle", self)

        window_row = QHBoxLayout()
        window_row.addWidget(QLabel("Capture window:", self))
        window_row.addWidget(self._spinbox)
        window_row.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(window_row)
        layout.addWidget(self._button)
        layout.addWidget(self._status_label)
        layout.addStretch()
        self.setLayout(layout)

    def _on_button_clicked(self):
        if self._running:
            self._stop_and_report()
        else:
            self._start()

    def _subprocess_threads(self):
        return [
            entry['Thread'] for entry in self.shared_data.RTAnalysisQueuesThreads
            if isinstance(entry['Thread'], AnalysisProcess_customFunction)
        ]

    def _start(self):
        top_n = self.shared_data.config.performance_config.hotspot_top_n
        self._capture = PerformanceCapture(
            get_thread_registry=lambda: dict(self.shared_data.perfThreadLabels),
            hotspot_top_n=top_n,
        )
        self._capture.start()
        for thread in self._subprocess_threads():
            thread.start_profiling()

        self._running = True
        self._button.setText("Stop Performance Mode")
        window_s = self._spinbox.value()
        self._status_label.setText(f"Capturing... (auto-stops in {window_s}s)")
        QTimer.singleShot(int(window_s * 1000), self._on_timer_elapsed)

    def _on_timer_elapsed(self):
        if self._running:
            self._stop_and_report()

    def _stop_and_report(self):
        self._running = False
        self._button.setText("Start Performance Mode")
        self._status_label.setText("Collecting subprocess reports...")

        subprocess_reports = []
        for thread in self._subprocess_threads():
            rep = thread.stop_profiling()
            if rep is not None:
                subprocess_reports.append(rep)

        report = self._capture.stop(subprocess_reports=subprocess_reports)
        self._status_label.setText(
            f"Last capture: {report.duration_s:.1f}s, {report.frames_rendered} frames"
        )
        dialog = PerformanceReportDialog(report, parent=self)
        dialog.exec_()
