"""
Rule-based placement pre-scorer.
Runs locally (<50ms, no API cost) and gives GPT a baseline to refine.
Scores are deliberately conservative — GPT adjusts up/down with context.
"""

from typing import List

# High-demand skills for Indian campus placements (2024-25)
TIER_A_SKILLS = {
    "python", "java", "c++", "data structures", "algorithms", "sql",
    "machine learning", "deep learning", "system design", "react",
    "node.js", "django", "fastapi", "aws", "docker", "kubernetes",
    "leetcode", "competitive programming", "tensorflow", "pytorch",
}

TIER_B_SKILLS = {
    "html", "css", "javascript", "git", "linux", "mongodb", "mysql",
    "flask", "spring boot", "typescript", "c", "r", "tableau",
    "power bi", "excel", "communication", "leadership",
}

COLLEGE_TIER_WEIGHTS = {
    "tier1": 1.3,   # IIT/NIT/BITS
    "tier2": 1.0,   # State engineering colleges
    "tier3": 0.75,  # Private/lesser-known colleges
}

YEAR_WEIGHTS = {
    "fresher": 0.85,
    "2nd": 0.80,
    "3rd": 1.0,
    "4th": 1.05,
}


def _cgpa_score(cgpa: float) -> int:
    """Map CGPA to a base score out of 40."""
    if cgpa >= 9.0:
        return 40
    elif cgpa >= 8.5:
        return 35
    elif cgpa >= 8.0:
        return 30
    elif cgpa >= 7.5:
        return 25
    elif cgpa >= 7.0:
        return 20
    elif cgpa >= 6.5:
        return 15
    elif cgpa >= 6.0:
        return 10
    else:
        return 5


def _skills_score(skills: List[str]) -> int:
    """Map skill set to a score out of 40."""
    normalized = {s.lower() for s in skills}

    tier_a_count = len(normalized & TIER_A_SKILLS)
    tier_b_count = len(normalized & TIER_B_SKILLS)

    # Tier A skills are worth 5pts each (max 30), Tier B worth 2pts each (max 10)
    score = min(tier_a_count * 5, 30) + min(tier_b_count * 2, 10)
    return score


def compute_base_score(
    cgpa: float,
    skills: List[str],
    college_tier: str,
    year: str,
) -> dict:
    """
    Returns a dict with:
      - base_score (0–100)
      - placement_low, placement_high (percentage range)
      - label: "Low" | "Moderate" | "Good" | "Strong"
      - breakdown: dict of sub-scores for transparency
    """
    raw_score = _cgpa_score(cgpa) + _skills_score(skills)  # 0–80

    tier_weight = COLLEGE_TIER_WEIGHTS.get(college_tier, 1.0)
    year_weight = YEAR_WEIGHTS.get(year, 1.0)

    adjusted = raw_score * tier_weight * year_weight
    base_score = min(int(adjusted), 100)

    # Convert score → probability range
    if base_score >= 75:
        low, high, label = 70, 90, "Strong"
    elif base_score >= 55:
        low, high, label = 50, 70, "Good"
    elif base_score >= 30:
        low, high, label = 25, 50, "Moderate"
    else:
        low, high, label = 10, 35, "Low"

    return {
        "base_score": base_score,
        "placement_low": low,
        "placement_high": high,
        "label": label,
        "breakdown": {
            "cgpa_score": _cgpa_score(cgpa),
            "skills_score": _skills_score(skills),
            "tier_weight": tier_weight,
            "year_weight": year_weight,
        },
    }
