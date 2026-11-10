import tempfile
from pathlib import Path

from license_detector.models import ClassificationResult
from reports.report_generator import generate_reports
from scanner.font_scanner import FontInfo


def _sample_results():
    info = FontInfo(
        file_path="C:/fonts/Test.ttf", file_name="Test.ttf", file_hash="hash1",
        family_name="TestFamily", full_name="TestFamily Regular", designer="Jane Doe",
        manufacturer="Acme", version="1.000",
    )
    result = ClassificationResult(
        category="OFL", confidence=0.93, source="Metadonnees embarquees",
        url="https://scripts.sil.org/OFL", reason="Motif OFL trouve.",
    )
    return [(info, result)]


def test_generate_reports_creates_all_three_files():
    with tempfile.TemporaryDirectory() as tmp:
        destination = Path(tmp)
        paths = generate_reports(_sample_results(), destination)

        assert Path(paths["csv"]).exists()
        assert Path(paths["xlsx"]).exists()
        assert Path(paths["html"]).exists()

        csv_content = Path(paths["csv"]).read_text(encoding="utf-8-sig")
        assert "TestFamily" in csv_content
        assert "OFL" in csv_content

        html_content = Path(paths["html"]).read_text(encoding="utf-8")
        assert "TestFamily" in html_content
        assert "93.0" in html_content or "93" in html_content
