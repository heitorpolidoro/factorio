# Recipe Tree Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App Streamlit (`streamlit run app.py`) que mostra a árvore de produção de qualquer item do Factorio a partir de `recipes.db`, navegável e com receitas alternativas selecionáveis por clique.

**Architecture:** Camada de dados pura em Python (`tree.py`) constrói a árvore recursivamente a partir de `recipes.db` (SQLite); `icons.py` resolve o ícone local de cada item com fallback; `graph.py` converte a árvore em nós/arestas do `streamlit-agraph`; `app.py` é a única camada com Streamlit, orquestrando busca, direção e clique-para-trocar-receita via `st.session_state`.

**Tech Stack:** Python 3.14, Streamlit 1.62, streamlit-agraph 0.0.45 (vis.js), SQLite (`recipes.db` já existente), Pillow (ícone de fallback), pytest.

## Global Constraints

- Git foi inicializado depois da spec ter sido escrita, especificamente para esta implementação (execução via subagent-driven-development, que exige commits por task). Cada task termina com um commit, como de costume nesse fluxo — a menção original a "sem git" valia para a fase de design, não para a implementação.
- App é um único processo (`streamlit run app.py`), sem servidor adicional.
- Sem limite de profundidade na árvore.
- Receitas com categoria `recycling` são sempre excluídas das candidatas.
- Receita padrão quando há mais de uma candidata = menor `id` em `recipes` (ordem original: base → space-age → quality).
- Ciclo/auto-loop: item já presente no caminho do ramo atual vira nó folha marcado, sem recursão.
- Download de ícones (Task 4, script separado de `app.py`) só roda com confirmação explícita do usuário no chat antes do lote completo — nunca dispara sozinho.
- Ambiente: venv em `.venv/` na raiz do projeto (`/Users/heitor/workspace/factorio`), dependências fixadas em `requirements.txt`.

---

### Task 1: Ambiente do projeto

**Files:**
- Create: `requirements.txt` (raiz do projeto)
- Verify: `.venv/` (venv já criado durante a exploração; reaproveitar)

**Interfaces:**
- Produces: ambiente Python com `streamlit`, `streamlit-agraph`, `pillow`, `pytest` instalados, usado por todas as tasks seguintes.

- [ ] **Step 1: Confirmar/gerar o venv**

```bash
cd /Users/heitor/workspace/factorio
test -d .venv || python3 -m venv .venv
source .venv/bin/activate
```

- [ ] **Step 2: Conferir `requirements.txt`**

Arquivo já deve existir na raiz do projeto com este conteúdo (criar se não existir):

```
streamlit==1.62.0
streamlit-agraph==0.0.45
pillow==12.3.0
pytest==9.1.1
```

- [ ] **Step 3: Instalar dependências**

```bash
source .venv/bin/activate
pip install --quiet -r requirements.txt
```

- [ ] **Step 4: Verificar imports**

```bash
source .venv/bin/activate
python3 -c "import streamlit, streamlit_agraph, PIL, pytest; print('ok')"
```

Expected: imprime `ok` sem erro.

---

### Task 2: Núcleo da árvore (`tree.py`)

**Files:**
- Create: `tree.py`
- Test: `tests/test_tree.py`

**Interfaces:**
- Consumes: `recipes.db` (tabelas `recipes(id, name, pack, categories, ...)`, `ingredients(recipe_id, kind, name, amount)`, `results(recipe_id, kind, name, amount)`).
- Produces (usado pelas Tasks 5 e 6):
  - `TreeNode` (dataclass): `node_id: str`, `item_name: str`, `kind: str`, `amount: float | None`, `recipe_name: str | None`, `recipe_pack: str | None`, `is_cycle: bool`, `has_alternatives: bool`, `children: list[TreeNode]`.
  - `item_exists(conn: sqlite3.Connection, item_name: str) -> bool`
  - `get_item_kind(conn: sqlite3.Connection, item_name: str) -> str | None`
  - `get_candidate_recipes(conn: sqlite3.Connection, item_name: str, direction: Literal["down","up"]) -> list[tuple[int, str, str]]` (retorna `(recipe_id, recipe_name, pack)`, sem receitas de `recycling`, ordenado por `id`)
  - `build_tree(conn: sqlite3.Connection, root_item: str, direction: Literal["down","up"], recipe_overrides: dict[str, int] | None = None) -> TreeNode` (levanta `ValueError` se `root_item` não existir)
  - `find_node_by_id(node: TreeNode, node_id: str) -> TreeNode | None`
  - `list_all_item_names(conn: sqlite3.Connection) -> list[str]`

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `tests/test_tree.py`:

```python
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
```

- [ ] **Step 2: Rodar os testes e confirmar que falham (módulo não existe)**

```bash
source .venv/bin/activate
python3 -m pytest tests/test_tree.py -v
```

Expected: `ModuleNotFoundError: No module named 'tree'` (ou falhas de coleta) em todos os testes.

- [ ] **Step 3: Implementar `tree.py`**

```python
"""Construção da árvore de produção do Factorio a partir de recipes.db."""
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
        ORDER BY r.id ASC
        """,
        (item_name,),
    ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


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
        raise ValueError(f"Item '{root_item}' não encontrado em recipes.db")

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

    chosen_id = overrides.get(node.item_name, candidates[0][0])
    chosen = next((c for c in candidates if c[0] == chosen_id), candidates[0])
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
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

```bash
source .venv/bin/activate
python3 -m pytest tests/test_tree.py -v
```

Expected: todos os testes `PASSED`.

---

### Task 3: Ícones — mapeamento e resolução local (`icons.py`)

**Files:**
- Create: `icons.py`
- Test: `tests/test_icons.py`

**Interfaces:**
- Produces (usado pela Task 4 e pela Task 5):
  - `ICONS_DIR: pathlib.Path` (módulo-level, `<projeto>/icons/`)
  - `wiki_title_variants(item_name: str) -> list[str]`
  - `icon_url(title: str) -> str`
  - `get_icon_path(item_name: str) -> pathlib.Path`

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `tests/test_icons.py`:

```python
import icons


def test_wiki_title_variants_simple_word():
    assert icons.wiki_title_variants("electronic-circuit") == ["Electronic circuit"]


def test_wiki_title_variants_three_words():
    assert icons.wiki_title_variants("iron-gear-wheel") == ["Iron gear wheel"]


def test_wiki_title_variants_with_trailing_number():
    variants = icons.wiki_title_variants("uranium-238")
    assert variants == ["Uranium 238", "Uranium-238"]


def test_wiki_title_variants_dedup_when_no_number():
    # 'productivity-module' não tem sufixo numérico: só uma variante.
    assert icons.wiki_title_variants("productivity-module") == ["Productivity module"]


def test_icon_url_replaces_spaces_with_underscore():
    url = icons.icon_url("Electronic circuit")
    assert url == (
        "https://wiki.factorio.com/images/thumb/"
        "Electronic_circuit.png/32px-Electronic_circuit.png"
    )


def test_get_icon_path_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    (tmp_path / "electronic-circuit.png").write_bytes(b"fake-png-bytes")

    result = icons.get_icon_path("electronic-circuit")

    assert result == tmp_path / "electronic-circuit.png"


def test_get_icon_path_missing_file_returns_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)

    result = icons.get_icon_path("nonexistent-item")

    assert result == tmp_path / "_fallback.png"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
source .venv/bin/activate
python3 -m pytest tests/test_icons.py -v
```

Expected: `ModuleNotFoundError: No module named 'icons'`.

- [ ] **Step 3: Implementar `icons.py`**

```python
"""Mapeamento de nomes internos para ícones da wiki do Factorio, com cache local."""
from __future__ import annotations

from pathlib import Path

ICONS_DIR = Path(__file__).resolve().parent / "icons"


def wiki_title_variants(item_name: str) -> list[str]:
    """Candidatos de título de página da wiki para item_name, em ordem de tentativa.

    Variante primária trata todo hífen como separador de palavra (cobre a
    maioria dos itens, ex: 'electronic-circuit' -> 'Electronic circuit').
    Variante secundária mantém um sufixo numérico grudado na palavra
    anterior com hífen (cobre nomes estilo isótopo, ex: 'uranium-238' ->
    'Uranium-238'). Só as diferentes da primária.
    """
    words = item_name.split("-")
    primary = " ".join(words)

    merged: list[str] = []
    for i, word in enumerate(words):
        if i > 0 and word.isdigit():
            merged[-1] = merged[-1] + "-" + word
        else:
            merged.append(word)
    secondary = " ".join(merged)

    titles = [primary]
    if secondary != primary:
        titles.append(secondary)
    return [t[0].upper() + t[1:] for t in titles]


def icon_url(title: str) -> str:
    slug = title.replace(" ", "_")
    return f"https://wiki.factorio.com/images/thumb/{slug}.png/32px-{slug}.png"


def get_icon_path(item_name: str) -> Path:
    candidate = ICONS_DIR / f"{item_name}.png"
    if candidate.exists():
        return candidate
    return ICONS_DIR / "_fallback.png"
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

```bash
source .venv/bin/activate
python3 -m pytest tests/test_icons.py -v
```

Expected: todos `PASSED`.

---

### Task 4: Script de download dos ícones (`scripts/fetch_icons.py`)

**Files:**
- Create: `scripts/fetch_icons.py`

**Interfaces:**
- Consumes: `icons.ICONS_DIR`, `icons.wiki_title_variants`, `icons.icon_url`, `tree.list_all_item_names`.
- Produces: arquivos `icons/<item_name>.png` (um por item/fluido do dataset) e `icons/_fallback.png`. Não expõe função nova para outras tasks — é um script standalone.

**Importante:** este script faz requests reais para `wiki.factorio.com`. Antes de
rodar o Step 3 (execução completa), confirme com o usuário no chat — ele já
combinou esse fluxo durante o design, mas a confirmação é por execução, não
uma autorização permanente.

- [ ] **Step 1: Implementar o script**

Criar `scripts/fetch_icons.py`:

```python
#!/usr/bin/env python3
"""Baixa e cacheia localmente os ícones dos itens/fluidos de recipes.db.

Uso: python3 scripts/fetch_icons.py
Não é chamado por app.py — roda manualmente, uma vez (ou para atualizar o cache).
"""
from __future__ import annotations

import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from icons import ICONS_DIR, icon_url, wiki_title_variants  # noqa: E402
from tree import list_all_item_names  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "recipes.db"
USER_AGENT = "Mozilla/5.0 (compatible; factorio-recipe-tree-explorer/0.1; local personal tool)"
DELAY_SECONDS = 0.5


def download_icon(item_name: str) -> bool:
    dest = ICONS_DIR / f"{item_name}.png"
    for title in wiki_title_variants(item_name):
        url = icon_url(title)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                dest.write_bytes(response.read())
            return True
        except (urllib.error.HTTPError, urllib.error.URLError):
            continue
    return False


def make_fallback_icon() -> None:
    from PIL import Image, ImageDraw

    dest = ICONS_DIR / "_fallback.png"
    if dest.exists():
        return
    img = Image.new("RGBA", (32, 32), (120, 120, 120, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([1, 1, 30, 30], outline=(80, 80, 80, 255), width=2)
    img.save(dest)


def main() -> None:
    ICONS_DIR.mkdir(exist_ok=True)
    make_fallback_icon()

    conn = sqlite3.connect(DB_PATH)
    names = list_all_item_names(conn)
    conn.close()

    missing = []
    for i, name in enumerate(names, 1):
        dest = ICONS_DIR / f"{name}.png"
        if dest.exists():
            continue
        ok = download_icon(name)
        print(f"[{i}/{len(names)}] {name}: {'ok' if ok else 'FALTOU'}")
        if not ok:
            missing.append(name)
        time.sleep(DELAY_SECONDS)

    print(f"\nConcluído. {len(names) - len(missing)}/{len(names)} ícones baixados.")
    if missing:
        print("Sem ícone (usando fallback), revisar manualmente depois:")
        for name in missing:
            print(f"  {name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Validar em uma amostra pequena, sem rodar o lote completo**

```bash
source .venv/bin/activate
python3 -c "
from scripts.fetch_icons import download_icon
for name in ['electronic-circuit', 'uranium-238', 'productivity-module-3', 'crude-oil']:
    print(name, download_icon(name))
"
```

Expected: `True` para os quatro (confere manualmente os PNGs gerados em `icons/`
com `file icons/electronic-circuit.png` etc — deve reportar `PNG image data`).
Se algum vier `False`, é candidato à lista de exceções mencionada nos riscos
da spec; não bloqueia o restante do plano.

- [ ] **Step 3: Rodar o lote completo (com confirmação do usuário no chat antes)**

```bash
source .venv/bin/activate
python3 scripts/fetch_icons.py
```

Expected: log linha a linha terminando em `Concluído. N/300 ícones baixados.`
Itens faltantes (se houver) ficam listados no final — não é um erro, o app
usa `_fallback.png` para eles.

---

### Task 5: Conversão da árvore para grafo (`graph.py`)

**Files:**
- Create: `graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `tree.TreeNode`, `icons.get_icon_path`.
- Produces (usado pela Task 6): `tree_to_agraph(root: TreeNode) -> tuple[list[Node], list[Edge]]` (tipos `streamlit_agraph.Node`/`Edge`).

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `tests/test_graph.py`:

```python
from graph import tree_to_agraph
from tree import TreeNode


def make_node(node_id, item_name, amount=None, is_cycle=False, has_alternatives=False):
    return TreeNode(
        node_id=node_id,
        item_name=item_name,
        kind="item",
        amount=amount,
        recipe_name=None,
        recipe_pack=None,
        is_cycle=is_cycle,
        has_alternatives=has_alternatives,
    )


def test_tree_to_agraph_root_and_child(tmp_path, monkeypatch):
    import icons

    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)

    root = make_node("0", "electronic-circuit")
    child = make_node("0.0", "copper-cable", amount=3.0, has_alternatives=True)
    root.children.append(child)

    nodes, edges = tree_to_agraph(root)

    assert [n.id for n in nodes] == ["0", "0.0"]
    assert nodes[0].shape == "circularImage"
    assert nodes[0].image == str(tmp_path / "_fallback.png")
    assert nodes[1].label == "★ copper-cable"
    assert len(edges) == 1
    assert edges[0].source == "0"
    assert edges[0].to == "0.0"
    assert edges[0].label == "×3"


def test_tree_to_agraph_cycle_node_has_no_image():
    root = make_node("0", "heavy-oil")
    cycle_child = make_node("0.1", "heavy-oil", amount=25.0, is_cycle=True)
    root.children.append(cycle_child)

    nodes, edges = tree_to_agraph(root)

    cycle_node = nodes[1]
    assert cycle_node.shape == "dot"
    assert cycle_node.color == "#e74c3c"
    assert not hasattr(cycle_node, "image")
    assert edges[0].label == "↻"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
source .venv/bin/activate
python3 -m pytest tests/test_graph.py -v
```

Expected: `ModuleNotFoundError: No module named 'graph'`.

- [ ] **Step 3: Implementar `graph.py`**

```python
"""Converte uma TreeNode em nós/arestas do streamlit-agraph."""
from __future__ import annotations

from streamlit_agraph import Edge, Node

from icons import get_icon_path
from tree import TreeNode

CYCLE_COLOR = "#e74c3c"
ALTERNATIVE_COLOR = "#f39c12"
DEFAULT_COLOR = "#7f8c8d"


def tree_to_agraph(root: TreeNode) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    _collect(root, nodes, edges)
    return nodes, edges


def _make_node(node: TreeNode) -> Node:
    label = ("★ " if node.has_alternatives else "") + node.item_name
    kwargs = {
        "id": node.node_id,
        "title": node.item_name,
        "label": label,
        "size": 25,
    }
    if node.is_cycle:
        kwargs["shape"] = "dot"
        kwargs["color"] = CYCLE_COLOR
    else:
        kwargs["shape"] = "circularImage"
        kwargs["image"] = str(get_icon_path(node.item_name))
        kwargs["color"] = ALTERNATIVE_COLOR if node.has_alternatives else DEFAULT_COLOR
    return Node(**kwargs)


def _edge_label(child: TreeNode) -> str:
    if child.is_cycle:
        return "↻"
    if child.amount is None:
        return ""
    return f"×{child.amount:g}"


def _collect(node: TreeNode, nodes: list[Node], edges: list[Edge]) -> None:
    nodes.append(_make_node(node))
    for child in node.children:
        edges.append(Edge(source=node.node_id, target=child.node_id, label=_edge_label(child)))
        _collect(child, nodes, edges)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

```bash
source .venv/bin/activate
python3 -m pytest tests/test_graph.py -v
```

Expected: todos `PASSED`.

---

### Task 6: App Streamlit (`app.py`)

**Files:**
- Create: `app.py`

**Interfaces:**
- Consumes: `tree.build_tree`, `tree.get_candidate_recipes`, `tree.list_all_item_names`, `tree.find_node_by_id`, `graph.tree_to_agraph`.
- Produces: nada consumido por outras tasks — é a entrada do app.

- [ ] **Step 1: Implementar `app.py`**

```python
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
```

- [ ] **Step 2: Rodar o app e verificar manualmente**

```bash
source .venv/bin/activate
streamlit run app.py
```

Checklist manual (confere no navegador que abre sozinho):

1. Item raiz padrão `electronic-circuit` aparece com sua árvore completa.
2. Trocar pra `productivity-module-3` na busca do sidebar mostra a árvore de
   3 níveis (com `advanced-circuit`/`processing-unit` repetidos em vários
   ramos).
3. Alternar o toggle de direção para `⬆ o que eu posso fazer` com
   `iron-plate` como raiz mostra pelo menos um filho (ex: `sulfuric-acid`).
4. Buscar `heavy-oil`: o nó `heavy-oil` que aparece como filho de
   `coal-liquefaction` (se essa for a receita escolhida) tem cor diferente
   (vermelho) e aresta rotulada `↻` — não trava em loop infinito.
5. Buscar `electronic-circuit`, clicar no nó `copper-cable` (tem `★` no
   rótulo): aparece o seletor "Receitas alternativas para copper-cable"
   abaixo do grafo, com `copper-cable (base)` e `casting-copper-cable
   (space-age)`. Trocar a seleção reconstrói a árvore com a nova receita.
6. Nós mostram o ícone (se `scripts/fetch_icons.py` já rodou) ou o ícone
   cinza de fallback, e o nome do item aparece ao passar o mouse (tooltip).

---

## Ordem de execução

Task 1 → Task 2 → Task 3 → (Task 4, requer confirmação de download no chat)
→ Task 5 → Task 6. Tasks 2 e 3 não dependem uma da outra e poderiam ser
paralelizadas; Task 4 depende de 2 e 3; Task 5 depende de 2 e 3; Task 6
depende de 2 e 5 (e se beneficia de 4 já ter rodado, mas funciona com
fallback mesmo sem ícones baixados).
