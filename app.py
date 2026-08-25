"""Recipe Tree Explorer — árvore de produção interativa do Factorio."""
import sqlite3
from pathlib import Path

import streamlit as st
from streamlit_agraph import Config, agraph

from graph import tree_to_agraph
from tree import build_tree, find_node_by_id, get_candidate_recipes, list_all_item_names

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

tree = build_tree(conn, root_item, direction, st.session_state.recipe_overrides)
nodes, edges = tree_to_agraph(tree)

config = Config(width=1200, height=750, directed=True, physics=False, hierarchical=True)
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
        current_id = st.session_state.recipe_overrides.get(item_name, candidates[0][0])
        labels = list(options.keys())
        current_label = next(label for label, recipe_id in options.items() if recipe_id == current_id)
        chosen_label = st.selectbox("Receita", labels, index=labels.index(current_label))
        chosen_id = options[chosen_label]
        if chosen_id != current_id:
            st.session_state.recipe_overrides[item_name] = chosen_id
            st.rerun()
