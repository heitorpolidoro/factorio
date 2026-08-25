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


def get_icon_bytes(item_name: str) -> bytes:
    """Bytes PNG do ícone (ou fallback), gerando um placeholder em memória
    se nem o ícone do item nem `_fallback.png` existirem em disco."""
    path = get_icon_path(item_name)
    if path.exists():
        return path.read_bytes()
    return _generate_placeholder_bytes()


def _generate_placeholder_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (32, 32), (120, 120, 120, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([1, 1, 30, 30], outline=(80, 80, 80, 255), width=2)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
