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
