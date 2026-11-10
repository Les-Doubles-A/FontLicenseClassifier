import tempfile
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder

from scanner.font_scanner import extract_font_info, iter_font_files


def _build_minimal_font(path: Path, license_description: str = "") -> None:
    """Construit un .ttf minimal (1 glyphe) avec des metadonnees de test."""
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({65: "A"})
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((0, 500)); pen.lineTo((500, 500)); pen.lineTo((500, 0)); pen.closePath()
    glyph = pen.glyph()
    fb.setupGlyf({".notdef": glyph, "A": glyph})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()

    name_strings = {
        "familyName": "TestFamily",
        "styleName": "Regular",
        "uniqueFontIdentifier": "TestFamily-Regular",
        "fullName": "TestFamily Regular",
        "version": "Version 1.000",
        "psName": "TestFamily-Regular",
    }
    fb.setupNameTable(name_strings)
    fb.font["name"].setName("John Doe", 9, 3, 1, 0x409)      # Designer
    fb.font["name"].setName("Acme Foundry", 8, 3, 1, 0x409)  # Manufacturer
    fb.font["name"].setName("Copyright 2024 Acme Foundry", 0, 3, 1, 0x409)
    if license_description:
        fb.font["name"].setName(license_description, 13, 3, 1, 0x409)

    fb.save(str(path))


def test_extract_font_info_reads_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        font_path = Path(tmp) / "TestFamily-Regular.ttf"
        _build_minimal_font(font_path, license_description="SIL Open Font License, Version 1.1")

        info = extract_font_info(font_path)

        assert info.is_valid
        assert info.family_name == "TestFamily"
        assert info.designer == "John Doe"
        assert info.manufacturer == "Acme Foundry"
        assert "Acme Foundry" in info.copyright
        assert "Open Font License" in info.embedded_license_description
        assert info.file_hash  # une empreinte a bien ete calculee


def test_extract_font_info_handles_invalid_file():
    with tempfile.TemporaryDirectory() as tmp:
        bad_path = Path(tmp) / "not_a_font.ttf"
        bad_path.write_bytes(b"this is not a real font file")

        info = extract_font_info(bad_path)

        assert not info.is_valid
        assert info.error is not None


def test_iter_font_files_finds_only_supported_extensions():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        font_path = root / "a.ttf"
        _build_minimal_font(font_path)
        (root / "readme.txt").write_text("not a font")
        (root / "subdir").mkdir()
        _build_minimal_font(root / "subdir" / "b.otf".replace(".otf", ".ttf"))

        found = list(iter_font_files(root))
        assert font_path in found
        assert len(found) == 2
