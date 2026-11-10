from license_detector.classifier import decide
from license_detector.models import Evidence


def test_decide_returns_unknown_with_no_evidence():
    result = decide([])
    assert result.category == "Unknown"
    assert result.confidence == 0.0


def test_decide_picks_highest_scoring_category():
    evidences = [
        Evidence(source="A", category="OFL", weight=0.9, confidence=0.9),
        Evidence(source="B", category="Commercial Use", weight=0.3, confidence=0.4),
    ]
    result = decide(evidences)
    assert result.category == "OFL"
    assert result.confidence > 0.5


def test_decide_falls_back_to_unknown_below_threshold():
    evidences = [Evidence(source="Web", category="Shareware", weight=0.35, confidence=0.3)]
    result = decide(evidences)
    assert result.category == "Unknown"


def test_decide_consensus_bonus_increases_confidence():
    single_source = [Evidence(source="A", category="MIT", weight=0.5, confidence=0.7)]
    two_sources = [
        Evidence(source="A", category="MIT", weight=0.5, confidence=0.7),
        Evidence(source="B", category="MIT", weight=0.4, confidence=0.6),
    ]
    result_single = decide(single_source)
    result_multi = decide(two_sources)
    assert result_multi.confidence >= result_single.confidence
