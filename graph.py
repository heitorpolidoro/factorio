"""Converts a TreeNode into streamlit-agraph nodes/edges."""
from __future__ import annotations

import base64

from streamlit_agraph import Edge, Node

from icons import get_icon_bytes
from tree import TreeNode

CYCLE_COLOR = "#e74c3c"
ALTERNATIVE_COLOR = "#f39c12"
DEFAULT_COLOR = "#7f8c8d"


def _encode_icon(item_name: str) -> str:
    data = get_icon_bytes(item_name)
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def tree_to_agraph(root: TreeNode) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    _collect(root, nodes, edges)
    return nodes, edges


def _make_node(node: TreeNode) -> Node:
    label = ("★ " if node.has_alternatives else "") + node.item_name
    kwargs = {
        "id": node.node_id,
        "title": node.item_name,
        "label": label,
        "size": 25,
    }
    if node.is_cycle:
        kwargs["shape"] = "dot"
        kwargs["color"] = CYCLE_COLOR
    else:
        kwargs["shape"] = "image"
        kwargs["image"] = _encode_icon(node.item_name)
        kwargs["color"] = ALTERNATIVE_COLOR if node.has_alternatives else DEFAULT_COLOR
    return Node(**kwargs)


def _edge_label(child: TreeNode) -> str:
    if child.is_cycle:
        return "↻"
    if child.amount is None:
        return ""
    return f"×{child.amount:g}"


def _collect(node: TreeNode, nodes: list[Node], edges: list[Edge]) -> None:
    nodes.append(_make_node(node))
    for child in node.children:
        edges.append(Edge(source=node.node_id, target=child.node_id, label=_edge_label(child)))
        _collect(child, nodes, edges)
