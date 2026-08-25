from graph import tree_to_agraph
from tree import TreeNode


def make_node(node_id, item_name, amount=None, is_cycle=False, has_alternatives=False):
    return TreeNode(
        node_id=node_id,
        item_name=item_name,
        kind="item",
        amount=amount,
        recipe_name=None,
        recipe_pack=None,
        is_cycle=is_cycle,
        has_alternatives=has_alternatives,
    )


def test_tree_to_agraph_root_and_child(tmp_path, monkeypatch):
    import icons

    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    (tmp_path / "_fallback.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes-for-test")

    root = make_node("0", "electronic-circuit")
    child = make_node("0.0", "copper-cable", amount=3.0, has_alternatives=True)
    root.children.append(child)

    nodes, edges = tree_to_agraph(root)

    assert [n.id for n in nodes] == ["0", "0.0"]
    assert nodes[0].shape == "circularImage"
    assert nodes[0].image.startswith("data:image/png;base64,")
    assert nodes[1].label == "★ copper-cable"
    assert len(edges) == 1
    assert edges[0].source == "0"
    assert edges[0].to == "0.0"
    assert edges[0].label == "×3"


def test_tree_to_agraph_cycle_node_has_no_image():
    root = make_node("0", "heavy-oil")
    cycle_child = make_node("0.1", "heavy-oil", amount=25.0, is_cycle=True)
    root.children.append(cycle_child)

    nodes, edges = tree_to_agraph(root)

    cycle_node = nodes[1]
    assert cycle_node.shape == "dot"
    assert cycle_node.color == "#e74c3c"
    assert not hasattr(cycle_node, "image")
    assert edges[0].label == "↻"


def test_tree_to_agraph_generates_placeholder_when_fallback_missing(tmp_path, monkeypatch):
    import icons

    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    # tmp_path is empty: no per-item icon file, no _fallback.png either.

    root = make_node("0", "some-item-with-no-icon-file")

    nodes, edges = tree_to_agraph(root)

    assert nodes[0].image.startswith("data:image/png;base64,")
