"""Recipe Tree Explorer — interactive Factorio production tree."""
import sqlite3
from pathlib import Path

import streamlit as st
from streamlit_agraph import Config, agraph

from graph import graph_to_agraph
from icons import get_icon_bytes
from tree import (
    build_down_graph,
    find_end_products,
    get_candidate_recipes,
    list_all_item_names,
    resolve_recipe_id,
)

DB_PATH = Path(__file__).parent / "recipes.db"

st.set_page_config(page_title="Factorio Recipe Tree Explorer", layout="wide")


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, check_same_thread=False)


if "recipe_overrides" not in st.session_state:
    st.session_state.recipe_overrides = {}
if "selected_node_item" not in st.session_state:
    st.session_state.selected_node_item = None

conn = get_connection()

st.sidebar.header("Recipe Tree Explorer")

item_names = list_all_item_names(conn)
default_index = item_names.index("electronic-circuit") if "electronic-circuit" in item_names else 0
root_item = st.sidebar.selectbox("Root item", item_names, index=default_index)

direction_label = st.sidebar.radio(
    "Direction",
    options=["⬆ what I need", "⬇ what I can make"],
)
direction = "down" if "what I need" in direction_label else "up"

if direction == "down":
    # The alternatives selector below only makes sense for a node that
    # belongs to the tree currently on screen. If the sidebar's root item or
    # direction changed since the last rerun, the previously clicked node may
    # no longer be part of the tree, so clear the stale selection first.
    current_root_direction = (root_item, direction)
    if st.session_state.get("last_root_direction") != current_root_direction:
        st.session_state.selected_node_item = None
        st.session_state.last_root_direction = current_root_direction

    graph = build_down_graph(conn, root_item, st.session_state.recipe_overrides)
    nodes, edges = graph_to_agraph(graph)

    config = Config(width=900, height=750, directed=True, physics=False, hierarchical=True)
    # Set directly on the nested layout dict rather than via Config(**kwargs):
    # the library also copies every kwarg onto the top-level config object,
    # which vis.js's options validator then flags as an "unknown option" (it
    # only recognizes these nested under layout.hierarchical).
    config.layout["hierarchical"]["direction"] = "RL"  # root on the right, ingredients fan out to the left
    config.layout["hierarchical"]["sortMethod"] = "directed"  # rank by edge direction (parent -> child), not node degree
    clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

    if clicked_node_id and clicked_node_id in graph.nodes:
        # Node ids are item names directly (build_down_graph dedupes by
        # item), so the clicked id is already the item to look up.
        st.session_state.selected_node_item = clicked_node_id

    if st.session_state.selected_node_item:
        item_name = st.session_state.selected_node_item
        candidates = get_candidate_recipes(conn, item_name, direction)
        if len(candidates) > 1:
            st.subheader(f"Alternative recipes for {item_name}")
            options = {f"{name} ({pack})": recipe_id for recipe_id, name, pack in candidates}
            # recipe_overrides is keyed by item name only (no direction/root scoping),
            # so a stored override id from a different direction's candidate set may
            # not exist among the current `candidates`. Fall back to the default
            # (lowest-id) recipe for display in that case instead of crashing.
            current_id = resolve_recipe_id(candidates, st.session_state.recipe_overrides, item_name)
            labels = list(options.keys())
            current_label = next(label for label, recipe_id in options.items() if recipe_id == current_id)
            chosen_label = st.selectbox("Recipe", labels, index=labels.index(current_label))
            chosen_id = options[chosen_label]
            if chosen_id != current_id:
                st.session_state.recipe_overrides[item_name] = chosen_id
                st.rerun()

else:
    # "what I can make" answers a different question than a production tree
    # can show cleanly: which items are true end products (nothing further
    # is ever made from them), no matter how many intermediate steps away.
    # A graph fanning out at every level would explode combinatorially for
    # a common item (electronic-circuit alone has 51 direct uses), so this
    # is a flat, deduplicated list instead of a tree.
    end_products = find_end_products(conn, root_item)
    st.subheader(f"Final products made from {root_item}")
    st.caption(f"{len(end_products)} end product{'s' if len(end_products) != 1 else ''} found")

    columns_per_row = 8
    for row_start in range(0, len(end_products), columns_per_row):
        row_items = end_products[row_start : row_start + columns_per_row]
        columns = st.columns(columns_per_row)
        for column, item_name in zip(columns, row_items):
            with column:
                st.image(get_icon_bytes(item_name), width=48)
                st.caption(item_name)
