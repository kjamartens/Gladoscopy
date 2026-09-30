"""Pure data types for the autonomous-microscopy flowchart.

These are framework-free containers (no Qt, no Nodz imports) shared between
the Qt dock widget, the recipe I/O layer, and the executor. Extracted from
`glados_pycromanager/GUI/FlowChart_dockWidgets.py` in Phase 8.2.
"""

from __future__ import annotations


class GladosGraph:
    """Code-form view of node connections in a scoring or acquisition flowchart.

    Holds the list of nodes participating in a graph and answers "which nodes
    are connected?" via the parent dock widget's `findNodeByName` lookup. The
    class itself does not import Qt or Nodz — it only borrows `findNodeByName`
    from whatever `parent` is passed in.
    """

    def __init__(self, parent):
        """Store the parent flowchart so node lookups can resolve later.

        Args:
            parent: The owning flowchart object. Must expose
                ``findNodeByName(name)``.
        """
        self.parent = parent
        self.nodes: list = []
        self.startNodeIndex: int = -1

    def addRawGraphEval(self, graphEval):
        """Populate ``self.nodes`` from a Nodz `evaluateGraph()` result.

        Args:
            graphEval: Iterable of (sender, receiver) pairs as returned by
                Nodz's ``evaluateGraph()``. Each endpoint is a
                ``"node_name.attr"`` string; the node name is the part before
                the first dot.
        """
        self.allNodeNames: list[str] = []
        for graphEvalPartFull in graphEval:
            for graphEvalPartFull2 in graphEvalPartFull:
                graphEvalPart = graphEvalPartFull2.split(".")[0]
                if graphEvalPart not in self.allNodeNames:
                    self.allNodeNames.append(graphEvalPart)

        for nodeName in self.allNodeNames:
            self.nodes.append(self.parent.findNodeByName(nodeName))
