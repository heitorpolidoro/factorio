import sqlite3
from pathlib import Path

import pytest

from tree import (
    build_down_graph,
    find_end_products,
    get_candidate_recipes,
    get_item_kind,
    item_exists,
    list_all_item_names,
    resolve_recipe_id,
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


def test_build_down_graph_raises_for_unknown_item(conn):
    with pytest.raises(ValueError):
        build_down_graph(conn, "not-a-real-item-xyz")


def test_build_down_graph_leaf_raw_material(conn):
    # crude-oil is never the result of any recipe in the dataset
    graph = build_down_graph(conn, "crude-oil")
    assert graph.nodes["crude-oil"].recipe_name is None
    assert graph.nodes["crude-oil"].has_alternatives is False
    assert graph.edges == []


def test_build_down_graph_default_recipe_is_lowest_id(conn):
    # copper-cable has 2 candidate recipes (excluding recycling): copper-cable (base, id 58)
    # and casting-copper-cable (space-age, id 265) — scrap-recycling (id 287) is excluded.
    graph = build_down_graph(conn, "copper-cable")
    node = graph.nodes["copper-cable"]
    assert node.recipe_name == "copper-cable"
    assert node.recipe_pack == "base"
    assert node.has_alternatives is True


def test_get_candidate_recipes_excludes_recycling(conn):
    candidates = get_candidate_recipes(conn, "copper-cable", "down")
    names = [name for _, name, _ in candidates]
    assert "scrap-recycling" not in names
    assert names == ["copper-cable", "casting-copper-cable"]


def test_build_down_graph_respects_override(conn):
    # 265 = casting-copper-cable
    graph = build_down_graph(conn, "copper-cable", recipe_overrides={"copper-cable": 265})
    node = graph.nodes["copper-cable"]
    assert node.recipe_name == "casting-copper-cable"
    assert node.recipe_pack == "space-age"


def test_build_down_graph_marks_self_loop_as_cycle_edge(conn):
    # 13 = coal-liquefaction, which consumes AND produces heavy-oil
    graph = build_down_graph(conn, "heavy-oil", recipe_overrides={"heavy-oil": 13})
    assert graph.nodes["heavy-oil"].recipe_name == "coal-liquefaction"
    cycle_edges = [e for e in graph.edges if e.source == "heavy-oil" and e.target == "heavy-oil"]
    assert len(cycle_edges) == 1
    assert cycle_edges[0].is_cycle is True
    assert cycle_edges[0].amount == 25.0
    # the cyclic reference does not spawn a second heavy-oil node
    assert sum(1 for name in graph.nodes if name == "heavy-oil") == 1


def test_build_down_graph_shares_node_across_multiple_parents(conn):
    # advanced-circuit needs copper-cable both directly (amount 4) and
    # indirectly via electronic-circuit (amount 3) — copper-cable must be a
    # single shared node with two incoming edges, not two separate
    # copper-cable subtrees each rebuilding copper-plate/copper-ore again.
    graph = build_down_graph(conn, "advanced-circuit")

    assert len(graph.nodes) == 11
    assert len(graph.edges) == 11  # one more than the 10-edge spanning tree, from the shared node

    copper_cable_edges = {(e.source, e.amount) for e in graph.edges if e.target == "copper-cable"}
    assert copper_cable_edges == {("electronic-circuit", 3.0), ("advanced-circuit", 4.0)}

    # copper-cable's own ingredient chain was only expanded once, not once
    # per parent that needed copper-cable.
    assert sum(1 for e in graph.edges if e.source == "copper-plate" and e.target == "copper-ore") == 1


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


def test_get_candidate_recipes_excludes_asteroid_crushing(conn):
    # iron-ore/copper-ore are only ever "produced" in this dataset by asteroid
    # crushing/reprocessing recipes (category "crushing") — excluding that
    # category leaves them with no candidates at all, i.e. true raw-material
    # leaves, instead of pulling in the asteroid-chunk cycle chain.
    assert get_candidate_recipes(conn, "iron-ore", "down") == []
    assert get_candidate_recipes(conn, "copper-ore", "down") == []


def test_build_down_graph_leaf_for_ore_after_excluding_asteroid_recipes(conn):
    graph = build_down_graph(conn, "electronic-circuit")
    assert graph.nodes["iron-ore"].recipe_name is None
    iron_ore_edges = [e for e in graph.edges if e.target == "iron-ore"]
    assert len(iron_ore_edges) == 1
    assert iron_ore_edges[0].is_cycle is False


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


def test_get_candidate_recipes_treats_raw_materials_as_leaves(conn):
    # coal and water each have a real recipe in the dataset (coal-synthesis,
    # ice-melting/steam-condensation) but are gathered directly in normal
    # play, so "down" must ignore those recipes and report no candidates.
    assert get_candidate_recipes(conn, "coal", "down") == []
    assert get_candidate_recipes(conn, "water", "down") == []


def test_raw_material_still_shows_its_real_consumers_going_up(conn):
    # The raw-material override only suppresses "down" (this item's own
    # production) — "up" (what it's used to make) must be unaffected.
    candidates = get_candidate_recipes(conn, "coal", "up")
    assert len(candidates) > 0


def test_build_down_graph_stops_at_raw_material_leaf(conn):
    graph = build_down_graph(conn, "coal")
    assert graph.nodes["coal"].recipe_name is None
    assert graph.edges == []
