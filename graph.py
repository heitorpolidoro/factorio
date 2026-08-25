"""Converts a ProductionGraph into streamlit-agraph nodes/edges."""
from __future__ import annotations

import base64

from streamlit_agraph import Edge, Node

from icons import get_icon_bytes
from tree import ProductionEdge, ProductionGraph, ProductionNode

CYCLE_COLOR = "#e74c3c"
ALTERNATIVE_COLOR = "#f39c12"
DEFAULT_COLOR = "#7f8c8d"


def _encode_icon(item_name: str) -> str:
    data = get_icon_bytes(item_name)
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def graph_to_agraph(graph: ProductionGraph) -> tuple[list[Node], list[Edge]]:
    nodes = [_make_node(node) for node in graph.nodes.values()]
    edges = [_make_edge(edge) for edge in graph.edges]
    return nodes, edges


def _make_node(node: ProductionNode) -> Node:
    label = ("★ " if node.has_alternatives else "") + node.item_name
    return Node(
        id=node.item_name,
        title=node.item_name,
        label=label,
        size=25,
        shape="image",
        image=_encode_icon(node.item_name),
        color=ALTERNATIVE_COLOR if node.has_alternatives else DEFAULT_COLOR,
    )


def _make_edge(edge: ProductionEdge) -> Edge:
    if edge.is_cycle:
        label = "↻"
    elif edge.amount is not None:
        label = f"×{edge.amount:g}"
    else:
        label = ""

    kwargs = {
        "source": edge.source,
        "target": edge.target,
        "label": label,
        # source/target still encode parent -> ingredient (needed for the
        # hierarchical layout's edge-direction ranking), but the arrowhead
        # is drawn at the "from" end so it visually points ingredient ->
        # product instead — matches how a crafting chain reads.
        "arrows": "from",
    }
    if edge.is_cycle:
        # Closes a loop back to an ancestor instead of a normal ingredient
        # edge — call that out visually rather than let it look identical
        # to an ordinary shared-node reference (e.g. iron-plate used twice).
        kwargs["color"] = CYCLE_COLOR
        kwargs["dashes"] = True
    return Edge(**kwargs)
