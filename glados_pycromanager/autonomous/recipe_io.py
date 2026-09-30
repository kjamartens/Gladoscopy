"""Recipe (graph JSON) load/save glue.

Thin wrappers over Nodz's inherited ``saveGraph`` / ``loadGraph_KM`` plus
the Qt file-dialog + counter-reset + status-message logic. Extracted from
``glados_pycromanager/GUI/FlowChart_dockWidgets.py`` in Phase 8.3.

Phase 10.6 adds :func:`validate_recipe` and :func:`load_recipe` on top
— pure-Python helpers that surface a typed :class:`RecipeError` on
malformed input. They are decoupled from Qt so they can be tested
without a display, and the existing :func:`load_graph_json` UI glue
calls them before handing off to Nodz.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from glados_pycromanager.errors import RecipeError

#: Current persisted recipe schema version. Bump when a non-backward-
#: compatible change to NODES / CONNECTIONS shapes lands; pair with a
#: migrator in :func:`load_recipe`.
RECIPE_SCHEMA_VERSION = 1
RECIPE_SCHEMA_VERSION_KEY = "schema_version"

#: Top-level keys a valid recipe JSON must carry. Other ``NODES_*``
#: keys are optional today — saveGraph emits a fixed set but legacy
#: files may be missing some, and those gaps must not block loading.
REQUIRED_RECIPE_KEYS: tuple[str, ...] = ("NODES", "CONNECTIONS")


def validate_recipe(data: Any, *, strict: bool = False) -> dict[str, Any]:
    """Validate the structure of a recipe-JSON payload.

    Checks:
      - ``data`` is a JSON object (dict at the top level).
      - The required keys :data:`REQUIRED_RECIPE_KEYS` are present.
      - ``NODES`` is a dict of node-name → node-info dict.
      - ``CONNECTIONS`` is a list of ``(source, target)`` 2-tuples or
        2-lists where each endpoint is a string ``"node.attr"`` that
        names a node listed in ``NODES``. Dangling endpoints fail.
      - If ``schema_version`` is present, it is an int and not greater
        than :data:`RECIPE_SCHEMA_VERSION`. When ``strict`` is True a
        missing version is itself an error.

    Args:
        data: The parsed JSON payload (output of :func:`json.load`).
        strict: When True, require ``schema_version`` to be present.

    Returns:
        The same ``data`` object, after successful validation.

    Raises:
        RecipeError: With a message identifying the first failure.
    """
    if not isinstance(data, dict):
        raise RecipeError(
            f"Recipe must be a JSON object, got {type(data).__name__}"
        )

    for key in REQUIRED_RECIPE_KEYS:
        if key not in data:
            raise RecipeError(f"Recipe is missing required key {key!r}")

    version = data.get(RECIPE_SCHEMA_VERSION_KEY)
    if version is None:
        if strict:
            raise RecipeError(
                f"Recipe is missing required {RECIPE_SCHEMA_VERSION_KEY!r}"
            )
    elif not isinstance(version, int) or version > RECIPE_SCHEMA_VERSION:
        raise RecipeError(
            f"Recipe has unsupported {RECIPE_SCHEMA_VERSION_KEY}={version!r} "
            f"(this build supports up to {RECIPE_SCHEMA_VERSION})"
        )

    nodes = data["NODES"]
    if not isinstance(nodes, dict):
        raise RecipeError(
            f"Recipe 'NODES' must be an object, got {type(nodes).__name__}"
        )
    for name, info in nodes.items():
        if not isinstance(name, str) or not name:
            raise RecipeError(
                f"Recipe 'NODES' has non-string node name {name!r}"
            )
        if not isinstance(info, dict):
            raise RecipeError(
                f"Recipe 'NODES'[{name!r}] must be an object, got "
                f"{type(info).__name__}"
            )

    connections = data["CONNECTIONS"]
    if not isinstance(connections, list):
        raise RecipeError(
            f"Recipe 'CONNECTIONS' must be a list, got "
            f"{type(connections).__name__}"
        )

    node_names = set(nodes)
    for idx, entry in enumerate(connections):
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise RecipeError(
                f"Recipe 'CONNECTIONS'[{idx}] must be a 2-element list, "
                f"got {entry!r}"
            )
        src, dst = entry
        for endpoint in (src, dst):
            if not isinstance(endpoint, str) or "." not in endpoint:
                raise RecipeError(
                    f"Recipe 'CONNECTIONS'[{idx}] endpoint {endpoint!r} is "
                    f"not a 'node.attribute' string"
                )
            node_part = endpoint[: endpoint.rfind(".")]
            if node_part not in node_names:
                raise RecipeError(
                    f"Recipe 'CONNECTIONS'[{idx}] references unknown node "
                    f"{node_part!r}"
                )

    return data


def load_recipe(path: str | Path, *, strict: bool = False) -> dict[str, Any]:
    """Read and validate a recipe JSON file.

    Args:
        path: Filesystem path to the recipe JSON.
        strict: Forwarded to :func:`validate_recipe`.

    Returns:
        The validated recipe dict.

    Raises:
        RecipeError: On any I/O failure, parse error, or schema
            violation. The original exception (if any) is chained.
    """
    path = str(path)
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise RecipeError(f"Recipe file {path!r} is unreadable: {exc}") from exc

    return validate_recipe(data, strict=strict)


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
