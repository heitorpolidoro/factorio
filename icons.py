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
