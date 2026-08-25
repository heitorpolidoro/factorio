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
