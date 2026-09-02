#!/usr/bin/env python3
"""
Factorio 2.0 / Space Age - Recipe & Crafting Tool

Mode: Recipe (formerly Recipe Query)
Features:
1. Craftable Items: Given a list of inventory items/ingredients, returns all direct items you can craft.
2. What I Need (Dependency DAG): Breaks down an item into required sub-ingredients down to raw materials.
3. What I Can Make (Usage & End Products): Shows direct uses and all downstream final products.
4. Recipe Info & Search: Inspect any recipe or item.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

DB_PATH = Path(__file__).parent / "recipes.db"
console = Console()

RAW_MATERIALS = frozenset({
    "coal",
    "iron-ore",
    "copper-ore",
    "stone",
    "uranium-ore",
    "crude-oil",
    "water",
    "wood",
    "raw-fish",
    "calcite",
    "tungsten-ore",
    "holmium-ore",
    "lithium-brine",
    "fluorine",
    "lava",
    "heavy-oil",
    "light-oil",
    "petroleum-gas",
})


@dataclass
class Ingredient:
    name: str
    kind: str
    amount: float


@dataclass
class Result:
    name: str
    kind: str
    amount: float


@dataclass
class Recipe:
    id: int
    name: str
    pack: str
    energy: float
    categories: List[str]
    subgroup: Optional[str]
    ingredients: List[Ingredient]
    results: List[Result]

    @property
    def ingredient_names(self) -> Set[str]:
        return {ing.name for ing in self.ingredients}

    @property
    def result_names(self) -> Set[str]:
        return {res.name for res in self.results}


def get_db_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        console.print(f"[bold red]Erro:[/bold red] Banco de dados [cyan]{db_path}[/cyan] não encontrado!")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_all_recipes(conn: sqlite3.Connection, include_recycling: bool = False, include_crushing: bool = True) -> List[Recipe]:
    query = "SELECT id, name, pack, energy_required, categories, subgroup, raw_json FROM recipes WHERE hidden = 0 ORDER BY id ASC"
    rows = conn.execute(query).fetchall()
    
    recipes = []
    for r in rows:
        rid = r["id"]
        cats = json.loads(r["categories"]) if r["categories"] else ["crafting"]
        
        if not include_recycling and any("recycling" in c for c in cats):
            continue
        if not include_crushing and any("crushing" in c for c in cats):
            continue

        ing_rows = conn.execute("SELECT name, kind, amount FROM ingredients WHERE recipe_id = ? ORDER BY id ASC", (rid,)).fetchall()
        ings = [Ingredient(name=i["name"], kind=i["kind"], amount=float(i["amount"])) for i in ing_rows]

        res_rows = conn.execute("SELECT name, kind, amount FROM results WHERE recipe_id = ? ORDER BY id ASC", (rid,)).fetchall()
        results = [Result(name=res["name"], kind=res["kind"], amount=float(res["amount"])) for res in res_rows]

        recipes.append(Recipe(
            id=rid,
            name=r["name"],
            pack=r["pack"],
            energy=float(r["energy_required"] or 0.5),
            categories=cats,
            subgroup=r["subgroup"],
            ingredients=ings,
            results=results
        ))
    return recipes


def list_all_items(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT DISTINCT name FROM ingredients UNION SELECT DISTINCT name FROM results ORDER BY name ASC").fetchall()
    return [r[0] for r in rows]


def find_craftable_recipes(
    recipes: List[Recipe],
    available_items: Set[str]
) -> Tuple[List[Recipe], List[Tuple[Recipe, Set[str]]]]:
    norm_available = {item.strip().lower() for item in available_items}
    fully_craftable = []
    missing_one = []

    for recipe in recipes:
        if not recipe.ingredients:
            continue
        req = recipe.ingredient_names
        diff = req - norm_available
        if len(diff) == 0:
            fully_craftable.append(recipe)
        elif len(diff) == 1:
            missing_one.append((recipe, diff))

    return fully_craftable, missing_one


def display_craftable(
    available_items: List[str],
    show_missing_one: bool = False,
    include_recycling: bool = False
):
    conn = get_db_connection()
    recipes = load_all_recipes(conn, include_recycling=include_recycling)
    norm_items = {i.strip().lower() for i in available_items if i.strip()}

    if not norm_items:
        console.print("[yellow]Nenhum item informado. Use:[/] [cyan]python3 recipe.py craft <item1> <item2> ...[/cyan]")
        return

    fully_craftable, missing_one = find_craftable_recipes(recipes, norm_items)

    inv_str = ", ".join(f"[bold cyan]{item}[/bold cyan]" for item in sorted(norm_items))
    console.print(Panel(
        f"[bold white]Itens no Inventário ({len(norm_items)}):[/bold white] {inv_str}",
        title="[bold green]FACTORIO - RECEITAS DIRETAS FABRICÁVEIS[/bold green]",
        border_style="green"
    ))

    if not fully_craftable:
        console.print("[bold yellow]Nenhum item direto pode ser fabricado exclusivamente com os itens selecionados.[/bold yellow]\n")
    else:
        table = Table(
            title=f"[bold green]✨ Itens que você consegue fabricar diretamente ({len(fully_craftable)} receitas)[/bold green]",
            header_style="bold magenta",
            border_style="bright_green"
        )
        table.add_column("Produto(s) Fabricado(s)", style="bold white", width=30)
        table.add_column("Receita", style="cyan", width=25)
        table.add_column("Ingredientes Necessários", style="yellow", width=36)
        table.add_column("Tempo", justify="right", style="dim white", width=8)
        table.add_column("Pack", justify="center", style="bold blue", width=12)

        for rec in sorted(fully_craftable, key=lambda r: r.name):
            products = ", ".join(
                f"[bold green]{res.name}[/bold green]" + (f" x{res.amount:g}" if res.amount != 1 else "")
                for res in rec.results
            )
            ingredients = ", ".join(
                f"{ing.name} [dim]({ing.amount:g})[/dim]"
                for ing in rec.ingredients
            )
            pack_badge = f"[cyan]{rec.pack}[/cyan]" if rec.pack == "base" else f"[magenta]{rec.pack}[/magenta]"
            table.add_row(
                products,
                rec.name,
                ingredients,
                f"{rec.energy:g}s",
                pack_badge
            )
        console.print(table)
        console.print()

    if show_missing_one and missing_one:
        m_table = Table(
            title=f"[bold yellow]⚠️ Quase fabricáveis (Falta apenas 1 ingrediente adicional) ({len(missing_one)} receitas)[/bold yellow]",
            header_style="bold magenta",
            border_style="yellow"
        )
        m_table.add_column("Produto(s)", style="white", width=28)
        m_table.add_column("Receita", style="cyan", width=22)
        m_table.add_column("Ingrediente Faltante", style="bold red", width=25)
        m_table.add_column("Ingredientes que você já tem", style="dim green", width=30)

        for rec, missing_set in sorted(missing_one, key=lambda x: x[0].name)[:25]:
            missing_item = list(missing_set)[0]
            products = ", ".join(f"{res.name}" + (f" x{res.amount:g}" if res.amount != 1 else "") for res in rec.results)
            has_ings = ", ".join(f"{ing.name} ({ing.amount:g})" for ing in rec.ingredients if ing.name in norm_items)
            m_table.add_row(
                products,
                rec.name,
                f"❌ {missing_item}",
                has_ings
            )
        console.print(m_table)
        console.print()


def display_need_tree(root_item: str):
    conn = get_db_connection()
    recipes = load_all_recipes(conn)
    item_lower = root_item.strip().lower()

    recipes_by_result = defaultdict(list)
    for r in recipes:
        for res in r.results:
            recipes_by_result[res.name].append(r)

    if item_lower not in recipes_by_result and item_lower in RAW_MATERIALS:
        console.print(f"[bold cyan]{item_lower}[/bold cyan] é uma matéria-prima direta (minério / recurso natural). Não possui receita de montagem.")
        return

    tree = Tree(f"[bold green]📦 {item_lower}[/bold green] (O que eu preciso)")

    def add_branches(parent_tree: Tree, current_item: str, visited: Set[str]):
        if current_item in RAW_MATERIALS:
            parent_tree.add(f"[dim yellow]⛏ {current_item} (Matéria-prima)[/dim yellow]")
            return

        cand_recipes = recipes_by_result.get(current_item, [])
        if not cand_recipes:
            parent_tree.add(f"[dim white]• {current_item} (Sem receita no banco)[/dim white]")
            return

        chosen_recipe = cand_recipes[0]
        for ing in chosen_recipe.ingredients:
            if ing.name in visited:
                parent_tree.add(f"[red]↻ {ing.name} (Ciclo detectado)[/red]")
            else:
                branch = parent_tree.add(f"[bold white]{ing.name}[/bold white] [cyan]x{ing.amount:g}[/cyan] [dim]({chosen_recipe.name})[/dim]")
                add_branches(branch, ing.name, visited | {ing.name})

    add_branches(tree, item_lower, {item_lower})
    console.print(tree)
    console.print()


def display_make_uses(root_item: str):
    conn = get_db_connection()
    recipes = load_all_recipes(conn)
    item_lower = root_item.strip().lower()

    direct_uses = []
    for r in recipes:
        if item_lower in r.ingredient_names:
            direct_uses.append(r)

    console.print(Panel(
        f"[bold white]Usos Diretos de:[/] [bold cyan]{item_lower}[/bold cyan] ({len(direct_uses)} receitas encontradas)",
        title="[bold green]FACTORIO - O QUE POSSO FAZER COM ESTE ITEM[/bold green]",
        border_style="cyan"
    ))

    if not direct_uses:
        console.print(f"[yellow]O item [bold]{item_lower}[/bold] não é ingrediente de nenhuma receita cadastrada (Produto Final).[/yellow]\n")
        return

    table = Table(header_style="bold magenta", border_style="cyan")
    table.add_column("Receita", style="bold white", width=26)
    table.add_column("Quantidade Usada", justify="right", style="cyan", width=16)
    table.add_column("Produtos Finais Produzidos", style="green", width=35)
    table.add_column("Outros Ingredientes", style="dim yellow", width=35)

    for rec in direct_uses:
        used_amount = sum(i.amount for i in rec.ingredients if i.name == item_lower)
        products = ", ".join(f"{res.name} (x{res.amount:g})" for res in rec.results)
        other_ings = ", ".join(f"{i.name} ({i.amount:g})" for i in rec.ingredients if i.name != item_lower) or "[dim]Nenhum[/dim]"
        table.add_row(rec.name, f"{used_amount:g}", products, other_ings)

    console.print(table)
    console.print()


def interactive_mode():
    conn = get_db_connection()
    all_items = list_all_items(conn)
    
    console.print("[bold yellow]=== MODO INTERATIVO DE RECEITAS (FACTORIO) ===[/bold yellow]")
    console.print("Digite os itens separados por espaço ou vírgula (ex: [cyan]iron-plate copper-plate electronic-circuit[/cyan]):")
    
    try:
        user_input = input("Itens disponíveis > ").strip()
        if not user_input:
            return
        items = [i.strip() for i in user_input.replace(",", " ").split() if i.strip()]
        display_craftable(items, show_missing_one=True)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Operação cancelada.[/dim]")


def main():
    parser = argparse.ArgumentParser(
        description="Factorio 2.0 / Space Age - Recipe & Crafting Tool (Modo Recipe)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a executar")

    craft_p = subparsers.add_parser("craft", aliases=["craftable"], help="Descobrir o que você pode fabricar com uma lista de itens")
    craft_p.add_argument("items", nargs="*", help="Lista de nomes de itens no inventário (ex: iron-plate copper-cable)")
    craft_p.add_argument("--missing-one", "-m", action="store_true", help="Mostrar também receitas onde falta apenas 1 ingrediente")
    craft_p.add_argument("--recycling", action="store_true", help="Incluir receitas de reciclagem")

    need_p = subparsers.add_parser("need", help="Árvore de dependências: O que eu preciso para fabricar este item")
    need_p.add_argument("item", help="Nome do item alvo (ex: electronic-circuit)")

    make_p = subparsers.add_parser("make", help="O que eu posso fazer: Receitas que usam este item")
    make_p.add_argument("item", help="Nome do ingrediente base (ex: iron-plate)")

    list_p = subparsers.add_parser("list", help="Listar todos os itens e fluidos disponíveis no banco")
    list_p.add_argument("--filter", "-f", help="Filtrar por nome")

    subparsers.add_parser("interactive", aliases=["ui"], help="Modo interativo no terminal")

    args = parser.parse_args()

    if not args.command or args.command in ("interactive", "ui"):
        if len(sys.argv) > 1 and not (args.command in ("interactive", "ui")):
            parser.print_help()
        else:
            interactive_mode()
    elif args.command in ("craft", "craftable"):
        if not args.items:
            interactive_mode()
        else:
            display_craftable(args.items, show_missing_one=args.missing_one, include_recycling=args.recycling)
    elif args.command == "need":
        display_need_tree(args.item)
    elif args.command == "make":
        display_make_uses(args.item)
    elif args.command == "list":
        conn = get_db_connection()
        items = list_all_items(conn)
        if args.filter:
            items = [i for i in items if args.filter.lower() in i.lower()]
        console.print(f"[bold green]Total de itens ({len(items)}):[/bold green]")
        console.print(", ".join(f"[cyan]{i}[/cyan]" for i in items))


if __name__ == "__main__":
    main()
