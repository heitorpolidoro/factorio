"""Converte uma TreeNode em nós/arestas do streamlit-agraph."""
from __future__ import annotations

from streamlit_agraph import Edge, Node

from icons import get_icon_path
from tree import TreeNode

CYCLE_COLOR = "#e74c3c"
ALTERNATIVE_COLOR = "#f39c12"
DEFAULT_COLOR = "#7f8c8d"


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
        kwargs["shape"] = "circularImage"
        kwargs["image"] = str(get_icon_path(node.item_name))
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
