"""Builds the Factorio production tree from recipes.db."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Literal, Optional

Direction = Literal["down", "up"]

# Items gathered directly (mined, pumped, farmed) rather than crafted, even
# though the game also offers alternate synthesis recipes for some of them
# (e.g. coal-synthesis, ice-melting). Always treated as leaves in the "down"
# direction — get_candidate_recipes() short-circuits to [] for these — so
# they read as a starting point rather than something to keep breaking down.
# Not exhaustive: extend as more of these turn up.
RAW_MATERIALS = frozenset(
    {
        "coal",
        "iron-ore",
        "copper-ore",
        "stone",
        "uranium-ore",
        "crude-oil",
        "water",
        "wood",
        "raw-fish",
    }
)


@dataclass
class ProductionNode:
    item_name: str
    kind: str
    recipe_name: Optional[str]
    recipe_pack: Optional[str]
    has_alternatives: bool


@dataclass
class ProductionEdge:
    source: str  # item_name of the recipe's own item (the one that needs `target`)
    target: str  # item_name of the ingredient
    amount: Optional[float]
    is_cycle: bool  # True if target is an ancestor of source in this expansion


@dataclass
class ProductionGraph:
    root: str
    nodes: dict[str, "ProductionNode"] = field(default_factory=dict)
    edges: list["ProductionEdge"] = field(default_factory=list)


def get_item_kind(conn: sqlite3.Connection, item_name: str) -> Optional[str]:
    row = conn.execute(
        """
        SELECT kind FROM (
            SELECT name, kind FROM ingredients
            UNION
            SELECT name, kind FROM results
        )
        WHERE name = ?
        LIMIT 1
        """,
        (item_name,),
    ).fetchone()
    return row[0] if row else None


def item_exists(conn: sqlite3.Connection, item_name: str) -> bool:
    return get_item_kind(conn, item_name) is not None


def get_candidate_recipes(
    conn: sqlite3.Connection, item_name: str, direction: Direction
) -> list[tuple[int, str, str]]:
    if direction == "down" and item_name in RAW_MATERIALS:
        return []

    join_table = "results" if direction == "down" else "ingredients"
    rows = conn.execute(
        f"""
        SELECT r.id, r.name, r.pack
        FROM recipes r
        JOIN {join_table} j ON j.recipe_id = r.id
        WHERE j.name = ?
          AND (r.categories IS NULL OR r.categories NOT LIKE '%"recycling"%')
          -- crushing = asteroid processing recipes (metallic/carbonic/oxide
          -- asteroid crushing and reprocessing), excluded so raw materials
          -- like iron-ore/copper-ore render as plain leaves instead of
          -- pulling in the asteroid-chunk cycle chain.
          AND (r.categories IS NULL OR r.categories NOT LIKE '%"crushing"%')
          -- hidden = map-editor/cheat-only recipes (e.g. loaders, infinity-chest),
          -- not craftable in normal play: exclude from candidates.
          -- NOTE: deliberately NOT filtering on `enabled` — 299/319 recipes have
          -- enabled = 0, which just means "not yet unlocked by tech" in a fresh
          -- game, not a reason to exclude the recipe from the tree.
          AND r.hidden = 0
        ORDER BY r.id ASC
        """,
        (item_name,),
    ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def resolve_recipe_id(
    candidates: list[tuple[int, str, str]], overrides: dict[str, int], item_name: str
) -> int:
    """Recipe id to use for item_name: the stored override if it's among
    the current candidates, otherwise the default (lowest-id) candidate."""
    candidate_ids = {c[0] for c in candidates}
    stored_id = overrides.get(item_name)
    return stored_id if stored_id in candidate_ids else candidates[0][0]


def _get_recipe_children_rows(
    conn: sqlite3.Connection, recipe_id: int, direction: Direction
) -> list[tuple[str, str, float]]:
    table = "ingredients" if direction == "down" else "results"
    rows = conn.execute(
        f"SELECT name, kind, amount FROM {table} WHERE recipe_id = ? ORDER BY id ASC",
        (recipe_id,),
    ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def build_down_graph(
    conn: sqlite3.Connection,
    root_item: str,
    recipe_overrides: Optional[dict[str, int]] = None,
) -> ProductionGraph:
    """Builds the "what I need" DAG for root_item: each item appears as
    exactly one node no matter how many places need it (e.g. iron-plate is
    one node with several incoming edges, not a separate copy per recipe
    that uses it). A node is expanded at most once — the first time it's
    reached — which also makes cycle detection trivial: by the time a
    cyclic reference is encountered the node is already in `graph.nodes`,
    so it's simply skipped rather than recursed into again.
    """
    if not item_exists(conn, root_item):
        raise ValueError(f"Item '{root_item}' not found in recipes.db")

    overrides = recipe_overrides or {}
    graph = ProductionGraph(root=root_item)
    _expand_down(conn, root_item, overrides, ancestors={root_item}, graph=graph)
    return graph


def _expand_down(
    conn: sqlite3.Connection,
    item_name: str,
    overrides: dict[str, int],
    ancestors: set[str],
    graph: ProductionGraph,
) -> None:
    candidates = get_candidate_recipes(conn, item_name, "down")
    node = ProductionNode(
        item_name=item_name,
        kind=get_item_kind(conn, item_name) or "item",
        recipe_name=None,
        recipe_pack=None,
        has_alternatives=len(candidates) > 1,
    )
    graph.nodes[item_name] = node
    if not candidates:
        return

    # Multiple candidates here are alternative recipes for producing the
    # *same* result — mutually exclusive, so pick one (with override) and
    # expand only its ingredients.
    chosen_id = resolve_recipe_id(candidates, overrides, item_name)
    chosen = next(c for c in candidates if c[0] == chosen_id)
    node.recipe_name, node.recipe_pack = chosen[1], chosen[2]

    rows = _get_recipe_children_rows(conn, chosen[0], "down")
    for child_name, _child_kind, child_amount in rows:
        is_cycle = child_name in ancestors
        already_built = child_name in graph.nodes
        graph.edges.append(
            ProductionEdge(source=item_name, target=child_name, amount=child_amount, is_cycle=is_cycle)
        )
        if not already_built:
            _expand_down(conn, child_name, overrides, ancestors | {child_name}, graph)


def list_all_item_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM ingredients UNION SELECT name FROM results ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def find_end_products(conn: sqlite3.Connection, root_item: str) -> list[str]:
    """Items reachable from root_item via "up" recipes (things it eventually
    helps make, transitively) that are never themselves used as an ingredient
    in anything further — i.e. true end products, not intermediate steps.

    Standard graph reachability (a single global `visited` set), not a tree
    walk: the same item is commonly reachable through many different paths,
    and a plain visited set naturally terminates on cycles too, since a
    revisited item is simply skipped rather than re-expanded.
    """
    visited: set[str] = set()
    end_products: set[str] = set()
    queue: list[str] = [root_item]

    while queue:
        item_name = queue.pop()
        if item_name in visited:
            continue
        visited.add(item_name)

        candidates = get_candidate_recipes(conn, item_name, "up")
        if not candidates:
            end_products.add(item_name)
            continue

        for recipe_id, _, _ in candidates:
            for child_name, _, _ in _get_recipe_children_rows(conn, recipe_id, "up"):
                if child_name not in visited:
                    queue.append(child_name)

    return sorted(end_products)
