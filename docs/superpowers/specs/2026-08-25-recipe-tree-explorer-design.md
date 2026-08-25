# Recipe Tree Explorer — Design

Date: 2026-08-25

## Objetivo

App Streamlit local (`streamlit run app.py`, um único comando) para explorar
visualmente as receitas de fabricação do Factorio a partir de `recipes.db`,
mostrando a árvore de produção de um item escolhido: o que é necessário para
fabricá-lo, ou o que pode ser fabricado a partir dele.

## Fora de escopo (v1)

- Autenticação, multiusuário, deploy remoto.
- Integração com `quality_calc.py` / `speed_calculator.py` / `upcycling_calculator.py`
  (pode virar uma aba futura, não faz parte desta spec).
- Edição do banco de dados pela UI.
- Suporte a mods de terceiros — só `base`, `space-age`, `quality`.

## Dados

Reaproveita `recipes.db` (SQLite), já criado, com as tabelas:

- `recipes(id, name, pack, enabled, hidden, energy_required, categories, subgroup, "order", icon, main_product, allow_productivity, allow_decomposition, auto_recycle, raw_json)`
- `ingredients(id, recipe_id, kind, name, amount, fluidbox_index)`
- `results(id, recipe_id, kind, name, amount, fluidbox_index, ignored_by_stats, ignored_by_productivity)`

Nenhuma migração de schema é necessária para esta feature.

## Algoritmo da árvore

Função central `build_tree(item_name, direction, recipe_overrides)`:

1. **Direção** (alternável na UI):
   - `down` ("o que eu preciso"): parte do item, busca receitas onde ele é
     **resultado** (join `results → recipes`), filhos são os `ingredients`
     dessa receita.
   - `up` ("o que eu posso fazer"): parte do item, busca receitas onde ele é
     **ingrediente** (join `ingredients → recipes`), filhos são os `results`
     dessa receita.
   - Mesma função recursiva para as duas direções; só troca qual tabela
     dirige a query.

2. **Filtro de reciclagem**: qualquer receita cujo `categories` contenha
   `"recycling"` é excluída da busca de candidatas (hoje só `scrap-recycling`
   no dataset — as receitas de reciclagem por item são geradas em tempo de
   jogo e não existem no `recipe.lua` extraído, então não aparecem no banco
   de qualquer forma).

3. **Escolha de receita quando há mais de uma candidata**: por padrão, a de
   menor `id` (ordem original de extração: `base` → `space-age` → `quality`,
   preservando a ordem do arquivo dentro de cada pack). O usuário pode
   sobrescrever por item clicando no nó (ver seção UI); a escolha fica em
   `st.session_state["recipe_overrides"][item_name] = recipe_id` e é
   respeitada em toda a árvore, não só no nó clicado.

4. **Ciclos / auto-loop**: a recursão mantém o caminho de itens já visitados
   (ancestrais no ramo atual). Se o próximo item candidato já está nesse
   caminho, o nó é criado como folha marcada `↻ já está na cadeia` e a
   recursão não continua por ali. Isso cobre tanto receitas de auto-loop
   (ex: `coal-liquefaction` consome e produz `heavy-oil`) quanto ciclos mais
   longos entre receitas.

5. **Itens sem receita** (matéria-prima, ex: minério bruto): viram folha sem
   necessidade de tratamento especial — a busca de candidatas simplesmente
   não retorna nada.

6. **Profundidade**: sem limite — a árvore é construída até o fim (folhas
   ou ciclos), sem paginação/lazy-load na v1.

## Ícones

- Cache local de imagens em `icons/<nome-interno>.png`, populado uma única
  vez (script de setup, não em toda execução do app).
- Mapeamento nome interno → nome da wiki: capitaliza a primeira letra de
  cada palavra, troca `-`/espaço por `_` (ex: `electronic-circuit` →
  `Electronic_circuit`). Testar contra uma amostra de ~15 nomes variados
  (incluindo casos como `uranium-238`, `empty-barrel`) antes de rodar para
  todos os ~300 itens/fluidos distintos usados em `ingredients`/`results`.
- URL: `https://wiki.factorio.com/images/thumb/<Nome>.png/32px-<Nome>.png`.
- Delay pequeno entre requests (não sobrecarregar a wiki).
- Nome que não resolver em nenhuma variação tentada: fica sem ícone próprio,
  usa um ícone genérico de fallback, e é logado para revisão manual depois.
- **Esse download só roda com confirmação explícita no chat antes de disparar
  os requests** — combinado com o usuário, não é uma ação silenciosa do app.
- Assets do jogo são propriedade da Wube Software; o cache é para uso local
  pessoal desta ferramenta, não para redistribuição.

## UI / Interação

- Streamlit, componente `streamlit-agraph` (wrapper de vis.js) para o grafo,
  em vez de imagem estática — necessário para clique-no-nó.
- Sidebar: campo de busca/autocomplete do item raiz; toggle de direção
  (⬇ o que preciso / ⬆ o que posso fazer).
- Nós do grafo usam o ícone como imagem (shape `circularImage`), com o nome
  do item como tooltip (hover). Nó sem ícone resolvido usa o ícone
  genérico de fallback.
- Nós cujo item tem mais de uma receita candidata (fora reciclagem) recebem
  uma marcação visual (badge) e ficam clicáveis.
- `agraph(...)` retorna o id do nó clicado. Se esse nó tem múltiplas
  receitas candidatas, um `st.selectbox` aparece logo abaixo do grafo listando
  as alternativas (nome da receita + pack); trocar a seleção grava em
  `recipe_overrides` e reconstrói a árvore inteira.
  - Nota de expectativa: o seletor aparece como um campo normal do Streamlit
    abaixo do grafo, não como um popover flutuante colado no nó (exigiria um
    componente React customizado, fora de escopo da v1).
- Arestas do grafo mostram a quantidade (`amount`) do ingrediente/resultado.

## Erros e casos de borda

- Item digitado que não existe em `ingredients`/`results`: mensagem de
  "item não encontrado", sem quebrar a árvore.
- Item existente mas sem nenhuma receita (matéria-prima) como raiz: mostra
  só o nó raiz, sem filhos, sem erro.
- Falha ao baixar um ícone específico: não interrompe o setup, só loga e usa
  o fallback (ver seção Ícones).

## Testes

- Testes automatizados (pytest) para `build_tree`: direção `down`/`up`,
  detecção de ciclo (`↻`), escolha de receita padrão (menor `id`), aplicação
  de `recipe_overrides`, filtro de categoria `recycling`, item sem receita
  (folha), item inexistente.
- Verificação manual no navegador: subir o app, buscar um item profundo
  (ex: `productivity-module-3`), alternar direção, clicar num nó com
  alternativas (ex: `copper-cable`) e confirmar que a árvore re-renderiza
  com a receita escolhida.

## Riscos conhecidos

- `streamlit-agraph` é uma lib de terceiros (não testada neste projeto
  ainda) — validar cedo na implementação que suporta nó com imagem +
  tooltip + retorno de clique como esperado.
- Mapeamento de nome para a wiki pode ter mais exceções do que o esperado
  além dos ~15 casos testados; lista de fallback deve ser revisada após o
  primeiro download completo.
