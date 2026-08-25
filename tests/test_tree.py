import sqlite3
from pathlib import Path

import pytest

from tree import (
    build_tree,
    find_node_by_id,
    get_candidate_recipes,
    get_item_kind,
    item_exists,
    list_all_item_names,
    TreeNode,
)

DB_PATH = Path(__file__).resolve().parent.parent / "recipes.db"


@pytest.fixture
def conn():
    connection = sqlite3.connect(DB_PATH)
    yield connection
    connection.close()


def test_item_exists_true(conn):
    assert item_exists(conn, "electronic-circuit") is True


def test_item_exists_false(conn):
    assert item_exists(conn, "not-a-real-item-xyz") is False


def test_get_item_kind(conn):
    assert get_item_kind(conn, "electronic-circuit") == "item"
    assert get_item_kind(conn, "petroleum-gas") == "fluid"


def test_build_tree_raises_for_unknown_item(conn):
    with pytest.raises(ValueError):
        build_tree(conn, "not-a-real-item-xyz", "down")


def test_build_tree_leaf_raw_material(conn):
    # crude-oil nunca é resultado de nenhuma receita no dataset
    tree = build_tree(conn, "crude-oil", "down")
    assert tree.item_name == "crude-oil"
    assert tree.children == []
    assert tree.recipe_name is None
    assert tree.has_alternatives is False


def test_build_tree_default_recipe_is_lowest_id(conn):
    # copper-cable tem 2 receitas candidatas (fora reciclagem): copper-cable (base, id 58)
    # e casting-copper-cable (space-age, id 265) — a scrap-recycling (id 287) é excluída.
    tree = build_tree(conn, "copper-cable", "down")
    assert tree.recipe_name == "copper-cable"
    assert tree.recipe_pack == "base"
    assert tree.has_alternatives is True


def test_get_candidate_recipes_excludes_recycling(conn):
    candidates = get_candidate_recipes(conn, "copper-cable", "down")
    names = [name for _, name, _ in candidates]
    assert "scrap-recycling" not in names
    assert names == ["copper-cable", "casting-copper-cable"]


def test_build_tree_respects_override(conn):
    # 265 = casting-copper-cable
    tree = build_tree(conn, "copper-cable", "down", recipe_overrides={"copper-cable": 265})
    assert tree.recipe_name == "casting-copper-cable"
    assert tree.recipe_pack == "space-age"


def test_build_tree_marks_self_loop_as_cycle(conn):
    # 13 = coal-liquefaction, que consome E produz heavy-oil
    tree = build_tree(conn, "heavy-oil", "down", recipe_overrides={"heavy-oil": 13})
    assert tree.recipe_name == "coal-liquefaction"
    cycle_children = [c for c in tree.children if c.item_name == "heavy-oil"]
    assert len(cycle_children) == 1
    cycle_node = cycle_children[0]
    assert cycle_node.is_cycle is True
    assert cycle_node.children == []
    assert cycle_node.amount == 25.0


def test_build_tree_direction_up(conn):
    # iron-plate como ingrediente: menor recipe_id entre quem o consome é 16 (sulfuric-acid)
    tree = build_tree(conn, "iron-plate", "up")
    assert tree.recipe_name == "sulfuric-acid"
    assert tree.has_alternatives is True
    assert len(tree.children) == 1
    assert tree.children[0].item_name == "sulfuric-acid"
    assert tree.children[0].kind == "fluid"
    assert tree.children[0].amount == 50.0


def test_find_node_by_id():
    root = TreeNode(node_id="0", item_name="a", kind="item", amount=None,
                     recipe_name=None, recipe_pack=None, is_cycle=False, has_alternatives=False)
    child = TreeNode(node_id="0.0", item_name="b", kind="item", amount=1.0,
                      recipe_name=None, recipe_pack=None, is_cycle=False, has_alternatives=False)
    root.children.append(child)

    assert find_node_by_id(root, "0.0") is child
    assert find_node_by_id(root, "0") is root
    assert find_node_by_id(root, "9.9") is None


def test_list_all_item_names_includes_known_items(conn):
    names = list_all_item_names(conn)
    assert "electronic-circuit" in names
    assert "crude-oil" in names
    assert names == sorted(names)
