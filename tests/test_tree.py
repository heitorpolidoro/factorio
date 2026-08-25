import sqlite3
from pathlib import Path

import pytest

from tree import (
    build_tree,
    find_end_products,
    find_node_by_id,
    get_candidate_recipes,
    get_item_kind,
    item_exists,
    list_all_item_names,
    resolve_recipe_id,
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
    # crude-oil is never the result of any recipe in the dataset
    tree = build_tree(conn, "crude-oil", "down")
    assert tree.item_name == "crude-oil"
    assert tree.children == []
    assert tree.recipe_name is None
    assert tree.has_alternatives is False


def test_build_tree_default_recipe_is_lowest_id(conn):
    # copper-cable has 2 candidate recipes (excluding recycling): copper-cable (base, id 58)
    # and casting-copper-cable (space-age, id 265) — scrap-recycling (id 287) is excluded.
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
    # 265 = casting-copper-cable (used as an explicit override)
    tree = build_tree(conn, "copper-cable", "down", recipe_overrides={"copper-cable": 265})
    assert tree.recipe_name == "casting-copper-cable"
    assert tree.recipe_pack == "space-age"


def test_build_tree_marks_self_loop_as_cycle(conn):
    # 13 = coal-liquefaction, which consumes AND produces heavy-oil
    tree = build_tree(conn, "heavy-oil", "down", recipe_overrides={"heavy-oil": 13})
    assert tree.recipe_name == "coal-liquefaction"
    cycle_children = [c for c in tree.children if c.item_name == "heavy-oil"]
    assert len(cycle_children) == 1
    cycle_node = cycle_children[0]
    assert cycle_node.is_cycle is True
    assert cycle_node.children == []
    assert cycle_node.amount == 25.0


def test_build_tree_direction_up_fans_out_every_candidate(conn):
    # "up" candidates aren't alternative recipes for the same result — each
    # one consumes iron-plate to make something different, so every one of
    # them shows up as a direct child instead of picking just one default.
    tree = build_tree(conn, "iron-plate", "up")
    assert tree.recipe_name is None
    assert tree.has_alternatives is False
    assert len(tree.children) == 44
    # recipe id 16 (sulfuric-acid) is the lowest id among iron-plate's
    # consumers, so its result is the first child.
    assert tree.children[0].item_name == "sulfuric-acid"
    assert tree.children[0].kind == "fluid"
    assert tree.children[0].amount == 50.0


def test_build_tree_direction_up_does_not_recurse_past_root(conn):
    # Fanning out at every depth (not just the root) would explode
    # combinatorially for a common item, so "up" nodes below the root stay
    # as leaves even though several of them have their own consumers.
    tree = build_tree(conn, "iron-plate", "up")
    assert all(child.children == [] for child in tree.children)


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


def test_get_candidate_recipes_excludes_hidden(conn):
    # express-loader (id 152) is hidden = 1 (a map-editor/cheat-only entity) and
    # must not appear among the candidates for express-transport-belt (up).
    candidates = get_candidate_recipes(conn, "express-transport-belt", "up")
    names = [name for _, name, _ in candidates]
    assert "express-loader" not in names


def test_build_tree_up_excludes_hidden_recipe_result(conn):
    # express-loader (id 152, hidden) must not contribute a child even under
    # the "fan out every candidate" up-direction behavior.
    tree = build_tree(conn, "express-transport-belt", "up")
    names = [c.item_name for c in tree.children]
    assert "express-loader" not in names
    assert names == ["turbo-transport-belt"]


def test_get_candidate_recipes_excludes_asteroid_crushing(conn):
    # iron-ore/copper-ore are only ever "produced" in this dataset by asteroid
    # crushing/reprocessing recipes (category "crushing") — excluding that
    # category leaves them with no candidates at all, i.e. true raw-material
    # leaves, instead of pulling in the asteroid-chunk cycle chain.
    assert get_candidate_recipes(conn, "iron-ore", "down") == []
    assert get_candidate_recipes(conn, "copper-ore", "down") == []


def test_build_tree_leaf_for_ore_after_excluding_asteroid_recipes(conn):
    tree = build_tree(conn, "electronic-circuit", "down")
    iron_plate = next(c for c in tree.children if c.item_name == "iron-plate")
    iron_ore = iron_plate.children[0]
    assert iron_ore.item_name == "iron-ore"
    assert iron_ore.children == []
    assert iron_ore.recipe_name is None
    assert iron_ore.is_cycle is False


def test_resolve_recipe_id_override_present_in_candidates():
    candidates = [(10, "recipe-a", "base"), (20, "recipe-b", "space-age")]
    overrides = {"widget": 20}
    assert resolve_recipe_id(candidates, overrides, "widget") == 20


def test_resolve_recipe_id_override_absent_falls_back_to_default():
    candidates = [(10, "recipe-a", "base"), (20, "recipe-b", "space-age")]
    # override id 999 doesn't match any candidate id
    overrides = {"widget": 999}
    assert resolve_recipe_id(candidates, overrides, "widget") == 10
    # override for a different item entirely — no entry for "widget"
    overrides_other_item = {"other-item": 20}
    assert resolve_recipe_id(candidates, overrides_other_item, "widget") == 10


def test_resolve_recipe_id_no_override_falls_back_to_default():
    candidates = [(10, "recipe-a", "base"), (20, "recipe-b", "space-age")]
    assert resolve_recipe_id(candidates, {}, "widget") == 10


def test_find_end_products_item_with_no_further_use_is_its_own_end_product(conn):
    # rocket-silo is never itself used as an ingredient in anything.
    assert find_end_products(conn, "rocket-silo") == ["rocket-silo"]


def test_find_end_products_transitive_and_deduplicated(conn):
    # uranium-238 feeds into several chains (nuclear fuel, weapons, science,
    # etc.) that all terminate in a small, exact set of end products.
    assert find_end_products(conn, "uranium-238") == [
        "atomic-bomb",
        "biolab",
        "captive-biter-spawner",
        "explosive-uranium-cannon-shell",
        "fusion-reactor-equipment",
        "nuclear-fuel",
        "spidertron",
        "uranium-cannon-shell",
        "uranium-rounds-magazine",
    ]


def test_find_end_products_terminates_on_cycles(conn):
    # heavy-oil's own "up" chain loops back on itself (e.g. via
    # coal-liquefaction, which both consumes and produces heavy-oil) — this
    # must terminate instead of looping forever, and still find real
    # end products beyond the cycle.
    products = find_end_products(conn, "heavy-oil")
    assert len(products) > 0
