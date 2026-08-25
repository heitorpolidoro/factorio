from graph import graph_to_agraph
from tree import ProductionEdge, ProductionGraph, ProductionNode


def make_node(item_name, has_alternatives=False):
    return ProductionNode(
        item_name=item_name,
        kind="item",
        recipe_name=None,
        recipe_pack=None,
        has_alternatives=has_alternatives,
    )


def test_graph_to_agraph_root_and_child(tmp_path, monkeypatch):
    import icons

    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    (tmp_path / "_fallback.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes-for-test")

    graph = ProductionGraph(root="electronic-circuit")
    graph.nodes["electronic-circuit"] = make_node("electronic-circuit")
    graph.nodes["copper-cable"] = make_node("copper-cable", has_alternatives=True)
    graph.edges.append(
        ProductionEdge(source="electronic-circuit", target="copper-cable", amount=3.0, is_cycle=False)
    )

    nodes, edges = graph_to_agraph(graph)

    nodes_by_id = {n.id for n in nodes}
    assert nodes_by_id == {"electronic-circuit", "copper-cable"}
    copper_node = next(n for n in nodes if n.id == "copper-cable")
    assert copper_node.shape == "image"
    assert copper_node.image.startswith("data:image/png;base64,")
    assert copper_node.label == "★ copper-cable"
    assert copper_node.color == "#f39c12"

    assert len(edges) == 1
    assert edges[0].source == "electronic-circuit"
    assert edges[0].to == "copper-cable"
    assert edges[0].label == "×3"
    # source/target still encode parent -> ingredient (for the hierarchical
    # layout's ranking), but the arrowhead is drawn at the "from" end so it
    # visually points ingredient -> product instead.
    assert edges[0].arrows == "from"


def test_graph_to_agraph_cycle_edge_is_marked(tmp_path, monkeypatch):
    import icons

    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    (tmp_path / "_fallback.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes-for-test")

    # A cycle-closing edge points back to an already-existing node (e.g.
    # heavy-oil -> heavy-oil via coal-liquefaction) — the node itself is
    # normal (still gets its icon), only the edge is marked.
    graph = ProductionGraph(root="heavy-oil")
    graph.nodes["heavy-oil"] = make_node("heavy-oil")
    graph.edges.append(ProductionEdge(source="heavy-oil", target="heavy-oil", amount=25.0, is_cycle=True))

    nodes, edges = graph_to_agraph(graph)

    assert nodes[0].shape == "image"
    assert nodes[0].image.startswith("data:image/png;base64,")
    assert edges[0].label == "↻"
    assert edges[0].color == "#e74c3c"
    assert edges[0].dashes is True


def test_graph_to_agraph_generates_placeholder_when_fallback_missing(tmp_path, monkeypatch):
    import icons

    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    # tmp_path is empty: no per-item icon file, no _fallback.png either.

    graph = ProductionGraph(root="some-item-with-no-icon-file")
    graph.nodes["some-item-with-no-icon-file"] = make_node("some-item-with-no-icon-file")

    nodes, edges = graph_to_agraph(graph)

    assert nodes[0].image.startswith("data:image/png;base64,")
