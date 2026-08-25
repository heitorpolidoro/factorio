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
) -> None:
    candidates = get_candidate_recipes(conn, node.item_name, direction)
    node.has_alternatives = len(candidates) > 1
    if not candidates:
        return

    chosen_id = resolve_recipe_id(candidates, overrides, node.item_name)
    chosen = next(c for c in candidates if c[0] == chosen_id)
    recipe_id, recipe_name, pack = chosen
    node.recipe_name = recipe_name
    node.recipe_pack = pack

    rows = _get_recipe_children_rows(conn, recipe_id, direction)
    for i, (child_name, child_kind, child_amount) in enumerate(rows):
        child_node_id = f"{node.node_id}.{i}"
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
            _expand(conn, child, direction, overrides, ancestors | {child_name})


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
