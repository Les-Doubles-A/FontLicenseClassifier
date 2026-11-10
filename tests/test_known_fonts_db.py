from license_detector.known_fonts_db import lookup, normalize_family


def test_normalize_strips_weight_suffixes():
    assert normalize_family("Roboto Bold") == normalize_family("Roboto")
    assert normalize_family("Open Sans Italic") == normalize_family("OpenSans")


def test_exact_match_found():
    evidences = lookup("Roboto")
    assert evidences
    assert evidences[0].category == "Apache License"


def test_unknown_family_returns_nothing_or_low_confidence():
    evidences = lookup("ThisFontDefinitelyDoesNotExistXYZ123")
    assert all(e.confidence < 0.9 for e in evidences)


def test_extra_entries_override_seed_lookup():
    extra = {normalize_family("MyCustomFont"): {"category": "GPL", "url": "", "publisher": "cache"}}
    evidences = lookup("MyCustomFont", extra_entries=extra)
    assert evidences and evidences[0].category == "GPL"
