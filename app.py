"""Recipe Tree Explorer — árvore de produção interativa do Factorio."""
import sqlite3
from pathlib import Path

import streamlit as st
from streamlit_agraph import Config, agraph

from graph import tree_to_agraph
from tree import (
    build_tree,
    find_node_by_id,
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
root_item = st.sidebar.selectbox("Item raiz", item_names, index=default_index)

direction_label = st.sidebar.radio(
    "Direção",
    options=["⬇ o que eu preciso", "⬆ o que eu posso fazer"],
)
direction = "down" if direction_label.startswith("⬇") else "up"

# The alternatives selector below only makes sense for a node that belongs to
# the tree currently on screen. If the sidebar's root item or direction
# changed since the last rerun, the previously clicked node may no longer be
# part of the tree (or may map to a disjoint set of candidate recipes), so
# clear the stale selection before it's used for anything.
current_root_direction = (root_item, direction)
if st.session_state.get("last_root_direction") != current_root_direction:
    st.session_state.selected_node_item = None
    st.session_state.last_root_direction = current_root_direction

tree = build_tree(conn, root_item, direction, st.session_state.recipe_overrides)
nodes, edges = tree_to_agraph(tree)

config = Config(width=900, height=750, directed=True, physics=False, hierarchical=True)
clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

if clicked_node_id:
    clicked_node = find_node_by_id(tree, clicked_node_id)
    if clicked_node:
        st.session_state.selected_node_item = clicked_node.item_name

if st.session_state.selected_node_item:
    item_name = st.session_state.selected_node_item
    candidates = get_candidate_recipes(conn, item_name, direction)
    if len(candidates) > 1:
        st.subheader(f"Receitas alternativas para {item_name}")
        options = {f"{name} ({pack})": recipe_id for recipe_id, name, pack in candidates}
        # recipe_overrides is keyed by item name only (no direction/root scoping),
        # so a stored override id from a different direction's candidate set may
        # not exist among the current `candidates`. Fall back to the default
        # (lowest-id) recipe for display in that case instead of crashing.
        current_id = resolve_recipe_id(candidates, st.session_state.recipe_overrides, item_name)
        labels = list(options.keys())
        current_label = next(label for label, recipe_id in options.items() if recipe_id == current_id)
        chosen_label = st.selectbox("Receita", labels, index=labels.index(current_label))
        chosen_id = options[chosen_label]
        if chosen_id != current_id:
            st.session_state.recipe_overrides[item_name] = chosen_id
            st.rerun()
