"""Maps internal item names to Factorio wiki icons, with a local cache."""
from __future__ import annotations

from pathlib import Path

ICONS_DIR = Path(__file__).resolve().parent / "icons"


def wiki_title_variants(item_name: str) -> list[str]:
    """Candidate wiki page titles for item_name, in try order.

    The primary variant treats every hyphen as a word separator (covers
    most items, e.g. 'electronic-circuit' -> 'Electronic circuit').
    The secondary variant keeps a trailing numeric segment attached to the
    previous word with a hyphen (covers isotope-style names, e.g.
    'uranium-238' -> 'Uranium-238'). Only included when different from
    the primary.
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
    """PNG bytes for the icon (or fallback), generating an in-memory
    placeholder if neither the item's icon nor `_fallback.png` exist on disk."""
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
