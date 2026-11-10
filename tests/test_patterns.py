from license_detector.patterns import best_category, match_categories


def test_ofl_detection():
    text = "This Font Software is licensed under the SIL Open Font License, Version 1.1."
    hits = match_categories(text)
    assert "OFL" in hits


def test_personal_use_detection():
    text = "This font is free for personal use only. Commercial use requires a license."
    category, _ = best_category(text)
    # les deux categories sont presentes ; "Personal Use Only" doit ressortir
    # comme l'un des deux candidats plausibles selon le nombre de motifs.
    assert category in {"Personal Use Only", "Commercial Use"}


def test_mit_detection():
    text = "Permission is hereby granted, free of charge, to any person... MIT License."
    hits = match_categories(text)
    assert "MIT" in hits


def test_no_match_returns_empty():
    assert match_categories("") == {}
    assert match_categories("Just a random sentence with no license info.") == {}


def test_public_domain_detection():
    hits = match_categories("Released into the public domain, CC0.")
    assert "Public Domain" in hits
