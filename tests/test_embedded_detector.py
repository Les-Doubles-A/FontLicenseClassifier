from license_detector import embedded_detector
from scanner.font_scanner import FontInfo


def _font_info(**overrides) -> FontInfo:
    base = dict(file_path="x.ttf", file_name="x.ttf", file_hash="abc")
    base.update(overrides)
    return FontInfo(**base)


def test_detects_ofl_from_license_description():
    info = _font_info(
        embedded_license_description=(
            "This Font Software is licensed under the SIL Open Font License, Version 1.1."
        )
    )
    evidences = embedded_detector.detect(info)
    categories = {e.category for e in evidences}
    assert "OFL" in categories
    assert all(e.weight == embedded_detector.BASE_WEIGHT for e in evidences)


def test_detects_commercial_from_copyright_all_rights_reserved():
    info = _font_info(copyright="Copyright (c) 2020 Acme Type Foundry. All rights reserved.")
    evidences = embedded_detector.detect(info)
    categories = {e.category for e in evidences}
    assert "Commercial Use" in categories


def test_no_evidence_when_no_text_available():
    info = _font_info()
    assert embedded_detector.detect(info) == []


def test_license_url_fallback_when_no_text_match():
    info = _font_info(embedded_license_url="https://scripts.sil.org/OFL")
    evidences = embedded_detector.detect(info)
    assert any(e.category == "OFL" for e in evidences)
