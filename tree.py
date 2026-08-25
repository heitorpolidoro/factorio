"""Builds the Factorio production tree from recipes.db."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Literal, Optional

Direction = Literal["down", "up"]


@dataclass
class TreeNode:
    node_id: str
    item_name: str
    kind: str
    amount: Optional[float]
    recipe_name: Optional[str]
    recipe_pack: Optional[str]
    is_cycle: bool
    has_alternatives: bool
    children: list["TreeNode"] = field(default_factory=list)


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


def build_tree(
    conn: sqlite3.Connection,
    root_item: str,
    direction: Direction,
    recipe_overrides: Optional[dict[str, int]] = None,
) -> TreeNode:
    if not item_exists(conn, root_item):
        raise ValueError(f"Item '{root_item}' not found in recipes.db")

    overrides = recipe_overrides or {}
    root = TreeNode(
        node_id="0",
        item_name=root_item,
        kind=get_item_kind(conn, root_item) or "item",
        amount=None,
        recipe_name=None,
        recipe_pack=None,
        is_cycle=False,
        has_alternatives=False,
    )
    _expand(conn, root, direction, overrides, ancestors={root_item})
    return root


def _expand(
    conn: sqlite3.Connection,
    node: TreeNode,
    direction: Direction,
    overrides: dict[str, int],
    ancestors: set[str],
    depth: int = 0,
) -> None:
    candidates = get_candidate_recipes(conn, node.item_name, direction)
    if not candidates:
        node.has_alternatives = False
        return

    if direction == "down":
        # Multiple candidates here are alternative recipes for producing the
        # *same* result — mutually exclusive, so pick one (with override) and
        # expand only its ingredients.
        node.has_alternatives = len(candidates) > 1
        chosen_id = resolve_recipe_id(candidates, overrides, node.item_name)
        chosen = next(c for c in candidates if c[0] == chosen_id)
        node.recipe_name, node.recipe_pack = chosen[1], chosen[2]
        rows = _get_recipe_children_rows(conn, chosen[0], direction)
        _add_children(conn, node, rows, direction, overrides, ancestors, depth)
        return

    # direction == "up": each candidate recipe consumes this item to make a
    # *different* product — these aren't alternatives for the same thing, so
    # every candidate's results are shown as siblings instead of picking one.
    node.has_alternatives = False
    node.recipe_name = None
    node.recipe_pack = None
    if depth > 0:
        # Only the root fans out. A common item (e.g. a basic circuit or
        # plate) can be used by 50+ recipes, each cascading into dozens
        # more — fanning out at every depth would explode combinatorially.
        # Search one of the results directly to keep exploring from there.
        return
    for recipe_id, _, _ in candidates:
        rows = _get_recipe_children_rows(conn, recipe_id, direction)
        _add_children(conn, node, rows, direction, overrides, ancestors, depth)


def _add_children(
    conn: sqlite3.Connection,
    node: TreeNode,
    rows: list[tuple[str, str, float]],
    direction: Direction,
    overrides: dict[str, int],
    ancestors: set[str],
    depth: int,
) -> None:
    for child_name, child_kind, child_amount in rows:
        child_node_id = f"{node.node_id}.{len(node.children)}"
        is_cycle = child_name in ancestors
        child = TreeNode(
            node_id=child_node_id,
            item_name=child_name,
            kind=child_kind,
            amount=child_amount,
            recipe_name=None,
            recipe_pack=None,
            is_cycle=is_cycle,
            has_alternatives=False,
        )
        node.children.append(child)
        if not is_cycle:
            _expand(conn, child, direction, overrides, ancestors | {child_name}, depth + 1)


def find_node_by_id(node: TreeNode, node_id: str) -> Optional[TreeNode]:
    if node.node_id == node_id:
        return node
    for child in node.children:
        found = find_node_by_id(child, node_id)
        if found:
            return found
    return None


def list_all_item_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM ingredients UNION SELECT name FROM results ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]
