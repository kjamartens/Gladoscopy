"""Recipe (graph JSON) load/save glue.

Thin wrappers over Nodz's inherited ``saveGraph`` / ``loadGraph_KM`` plus
the Qt file-dialog + counter-reset + status-message logic. Extracted from
``glados_pycromanager/GUI/FlowChart_dockWidgets.py`` in Phase 8.3.

Schema-level validation lives in Phase 10.6, not here. These functions
preserve the original behavior 1:1.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFileDialog, QMessageBox


def store_graph_json(flowchart) -> None:
    """Prompt for a path and persist the flowchart graph to JSON.

    Args:
        flowchart: A ``GladosNodzFlowChart_dockWidget``-like object exposing
            ``saveGraph(filename)`` (inherited from Nodz).
    """
    filename, _ = QFileDialog.getSaveFileName(flowchart, "Save file", "", "JSON files (*.json)")
    if filename:
        if not filename.endswith(".json"):
            filename += ".json"
        flowchart.saveGraph(filename)


def load_graph_json(flowchart) -> None:
    """Prompt for a JSON file, clear the current graph, and load it.

    Resets every per-node-type counter to zero before delegating to Nodz's
    ``loadGraph_KM``. On failure pops a Qt warning dialog (matches legacy
    behavior). Phase 10.6 adds schema validation on top.

    Args:
        flowchart: A ``GladosNodzFlowChart_dockWidget``-like object exposing
            ``clearGraph()``, ``nodes``, ``nodeInfo``, ``loadGraph_KM(path)``,
            and ``shared_data.warningErrorInfoInfo``.
    """
    filename, _ = QFileDialog.getOpenFileName(flowchart, "Open file", "", "JSON files (*.json)")
    if not filename:
        return

    try:
        flowchart.clearGraph()
        flowchart.nodes = []
        for nodeType in flowchart.nodeInfo:
            if nodeType[:2] != "__":
                flowchart.nodeInfo[nodeType]["NodeCounter"] = 0
                flowchart.nodeInfo[nodeType]["NodeCounterNeverReset"] = 0
        flowchart.loadGraph_KM(filename)
        flowchart.shared_data.warningErrorInfoInfo["Info"]["Other"] = ["Loaded " + filename]
    except Exception:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText("Could not load file: " + filename)
        msg.setWindowTitle("Warning")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
