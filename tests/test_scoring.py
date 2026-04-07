"""
Unit tests for the rule-based scoring engine.
Run with: pytest tests/test_scoring.py -v
No DB or API keys required.
"""
from app.services.scoring_service import compute_base_score


def test_strong_student():
    result = compute_base_score(
        cgpa=9.2,
        skills=["Python", "Machine Learning", "System Design", "AWS", "Docker", "React"],
        college_tier="tier1",
        year="4th",
    )
    assert result["label"] == "Strong"
    assert result["placement_high"] >= 70


def test_average_tier2_student():
    result = compute_base_score(
        cgpa=7.0,
        skills=["Python", "HTML", "CSS", "Git"],
        college_tier="tier2",
        year="3rd",
    )
    assert result["label"] in ("Moderate", "Good")
    assert 20 <= result["placement_low"] <= 60


def test_low_cgpa_few_skills():
    result = compute_base_score(
        cgpa=5.5,
        skills=["HTML"],
        college_tier="tier3",
        year="fresher",
    )
    assert result["label"] == "Low"
    assert result["placement_low"] <= 25


def test_score_bounds():
    result = compute_base_score(
        cgpa=10.0,
        skills=["Python", "Java", "C++", "Data Structures", "Algorithms",
                "SQL", "Machine Learning", "System Design", "AWS", "Docker"],
        college_tier="tier1",
        year="4th",
    )
    assert 0 <= result["base_score"] <= 100
    assert result["placement_low"] <= result["placement_high"]
