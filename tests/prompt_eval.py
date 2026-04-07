"""
PROMPT EVALUATION FRAMEWORK
=============================
Regression test all 3 prompts against representative Indian student profiles.
Run: python -m tests.prompt_eval  (from project root)
Requires: OPENAI_API_KEY in environment
"""

import asyncio
import json
from openai import AsyncOpenAI

client = AsyncOpenAI()  # reads OPENAI_API_KEY from env

# ── Test cases (representative Indian student profiles) ─────────────────────

TEST_PROFILES = [
    {
        "id": "weak_tier3",
        "desc": "Struggling Tier 3 student — realistic failure case",
        "cgpa": 5.8,
        "college_tier": "tier3",
        "year": "4th",
        "skills": ["HTML", "CSS"],
        "target_roles": ["Software Engineer"],
        "target_companies": ["TCS", "Infosys"],
        "resume_snippet": "B.Tech Computer Science, XYZ Private Engineering College. CGPA: 5.8. Skills: HTML, CSS, MS Office. Project: College Website using HTML.",
        "expected_label": "Low",
        "expected_ats_range": (20, 45),
        "expected_prob_range": (10, 35),
    },
    {
        "id": "average_tier2",
        "desc": "Average Tier 2 student — most common case",
        "cgpa": 7.2,
        "college_tier": "tier2",
        "year": "3rd",
        "skills": ["Python", "SQL", "HTML", "CSS", "Git"],
        "target_roles": ["Software Engineer", "Data Analyst"],
        "target_companies": ["Wipro", "Capgemini", "Zoho"],
        "resume_snippet": "B.Tech CSE, State Engineering College, CGPA 7.2. Projects: Library Management System (Python, MySQL). Blood Bank System (HTML, CSS, PHP). Skills: Python, SQL, Git. No internship. No LeetCode mentioned.",
        "expected_label": "Moderate",
        "expected_ats_range": (45, 65),
        "expected_prob_range": (30, 55),
    },
    {
        "id": "strong_tier2_dsa",
        "desc": "Strong Tier 2 student with DSA — upwardly mobile case",
        "cgpa": 8.1,
        "college_tier": "tier2",
        "year": "4th",
        "skills": ["Python", "Java", "DSA", "SQL", "React", "Node.js", "Docker"],
        "target_roles": ["SDE", "Backend Engineer"],
        "target_companies": ["Amazon", "Flipkart", "Razorpay", "Juspay"],
        "resume_snippet": "B.Tech CSE, Ramaiah Institute, CGPA 8.1. LeetCode: 350+ problems solved (Knight badge). Internship: Backend Intern at early-stage startup (3 months, Python, FastAPI). Projects: URL Shortener with Redis (deployed on Render), E-commerce API. Skills: Python, Java, DSA, SQL, React, Docker, Git.",
        "expected_label": "Good",
        "expected_ats_range": (65, 85),
        "expected_prob_range": (50, 75),
    },
    {
        "id": "tier1_strong",
        "desc": "IIT student — high benchmark",
        "cgpa": 8.8,
        "college_tier": "tier1",
        "year": "4th",
        "skills": ["C++", "Python", "System Design", "ML", "AWS", "Kubernetes"],
        "target_roles": ["SDE", "ML Engineer"],
        "target_companies": ["Google", "Microsoft", "Amazon", "Atlassian"],
        "resume_snippet": "B.Tech CSE, IIT Roorkee, CGPA 8.8. Codeforces: Expert (1700+). Research Intern: IISc Bangalore (NLP). Projects: Distributed Cache Implementation (C++), Sentiment Analysis API (Python, HuggingFace, deployed). Skills: C++, Python, System Design, AWS, Kubernetes.",
        "expected_label": "Strong",
        "expected_ats_range": (80, 100),
        "expected_prob_range": (70, 90),
    },
]


# ── Scoring rubric ──────────────────────────────────────────────────────────

def score_ats_output(result: dict, expected: dict) -> dict:
    """Score ATS prompt output against expected ranges."""
    issues = []
    score  = 100

    ats = result.get("ats_score", -1)
    lo, hi = expected["expected_ats_range"]
    if not (lo <= ats <= hi):
        issues.append(f"ATS score {ats} outside expected {lo}–{hi}")
        score -= 30

    if not result.get("strengths"):
        issues.append("Missing strengths"); score -= 10
    if not result.get("weaknesses"):
        issues.append("Missing weaknesses"); score -= 10
    if not result.get("missing_keywords"):
        issues.append("Missing keywords list"); score -= 10
    if not result.get("one_line_verdict"):
        issues.append("Missing one_line_verdict"); score -= 15

    # Check for new dimension_scores field
    if not result.get("dimension_scores"):
        issues.append("Missing dimension_scores"); score -= 10

    # Specificity check: weaknesses should not be generic
    for w in result.get("weaknesses", []):
        if len(w) < 20:
            issues.append(f"Weakness too short/generic: '{w}'"); score -= 5

    return {"score": max(0, score), "issues": issues}


def score_scoring_output(result: dict, expected: dict) -> dict:
    """Score placement scoring prompt output."""
    issues = []
    score  = 100

    label = result.get("label", "")
    if label != expected["expected_label"]:
        issues.append(f"Label '{label}' != expected '{expected['expected_label']}'")
        score -= 25

    lo_r = result.get("placement_low",  0)
    hi_r = result.get("placement_high", 0)
    exp_lo, exp_hi = expected["expected_prob_range"]
    if not (exp_lo <= lo_r <= exp_hi + 10):
        issues.append(f"placement_low {lo_r} out of expected range")
        score -= 20

    range_width = hi_r - lo_r
    if range_width < 15 or range_width > 30:
        issues.append(f"Range width {range_width} should be 15–25 points")
        score -= 15

    if not result.get("reasoning") or len(result.get("reasoning","")) < 50:
        issues.append("Reasoning too short"); score -= 15

    if not result.get("fastest_improvement"):
        issues.append("Missing fastest_improvement"); score -= 10

    # Check for new company_fit field
    if not result.get("company_fit"):
        issues.append("Missing company_fit"); score -= 10

    return {"score": max(0, score), "issues": issues}


def score_plan_output(result: dict) -> dict:
    """Score action plan prompt output."""
    issues = []
    score  = 100

    weeks = result.get("weeks", [])
    if len(weeks) != 6:
        issues.append(f"Expected 6 weeks, got {len(weeks)}"); score -= 20

    # Specificity check on tasks
    generic_phrases = ["practice dsa", "work on projects", "study hard", "improve your skills", "learn more"]
    for week in weeks:
        for task in week.get("tasks", []):
            task_lower = task.lower()
            for gp in generic_phrases:
                if gp in task_lower:
                    issues.append(f"Generic task detected: '{task[:60]}'")
                    score -= 8
                    break
            if len(task) < 40:
                issues.append(f"Task too short (likely vague): '{task}'")
                score -= 5

    # Resources check
    for week in weeks:
        resources = week.get("resources", [])
        if len(resources) < 2:
            issues.append(f"Week {week.get('week')} has too few resources")
            score -= 5

    if not result.get("motivational_note") or len(result.get("motivational_note","")) < 60:
        issues.append("Motivational note missing or too short"); score -= 10

    if not result.get("priority_skills"):
        issues.append("Missing priority_skills"); score -= 10

    return {"score": max(0, score), "issues": issues}


# ── Runner ──────────────────────────────────────────────────────────────────

async def run_eval():
    from app.prompts.ats_prompt     import build_ats_prompt, SYSTEM_PROMPT as ATS_SYS
    from app.prompts.scoring_prompt import build_scoring_prompt, SYSTEM_PROMPT as SCORING_SYS
    from app.prompts.plan_prompt    import build_plan_prompt, SYSTEM_PROMPT as PLAN_SYS
    from app.services.scoring_service import compute_base_score

    print("\n" + "="*60)
    print("PLACEMENTCOACH PROMPT EVALUATION")
    print("="*60)

    total_ats = total_scoring = total_plan = 0

    for profile in TEST_PROFILES:
        print(f"\n{'─'*50}")
        print(f"TEST: {profile['id']} — {profile['desc']}")
        print(f"{'─'*50}")

        base = compute_base_score(profile["cgpa"], profile["skills"], profile["college_tier"], profile["year"])

        # ATS eval
        ats_prompt = build_ats_prompt(profile["resume_snippet"], profile["target_roles"], profile["target_companies"])
        ats_res = await _call(ATS_SYS, ats_prompt, max_tokens=1200, temp=0.2)
        ats_eval = score_ats_output(ats_res, profile)
        print(f"  ATS  → score {ats_res.get('ats_score')}, eval: {ats_eval['score']}/100")
        for issue in ats_eval["issues"]: print(f"    ⚠ {issue}")

        # Scoring eval
        scoring_prompt = build_scoring_prompt(
            profile["resume_snippet"], profile["cgpa"], profile["skills"],
            profile["college_tier"], profile["year"],
            profile["target_roles"], profile["target_companies"], base
        )
        sc_res  = await _call(SCORING_SYS, scoring_prompt, max_tokens=1000, temp=0.3)
        sc_eval = score_scoring_output(sc_res, profile)
        print(f"  PROB → {sc_res.get('placement_low')}%–{sc_res.get('placement_high')}% [{sc_res.get('label')}], eval: {sc_eval['score']}/100")
        for issue in sc_eval["issues"]: print(f"    ⚠ {issue}")

        # Plan eval
        plan_prompt = build_plan_prompt(
            profile["cgpa"], profile["skills"], profile["college_tier"], profile["year"],
            profile["target_roles"],
            ["No projects", "No LeetCode"],
            ["DSA", "System Design"],
            sc_res.get("label", "Moderate"),
            sc_res.get("reasoning", ""),
            formatting_issues=ats_res.get("formatting_issues", []),
            company_fit=sc_res.get("company_fit"),
        )
        plan_res  = await _call(PLAN_SYS, plan_prompt, max_tokens=2000, temp=0.5)
        plan_eval = score_plan_output(plan_res)
        weeks = plan_res.get("weeks", [])
        print(f"  PLAN → {len(weeks)} weeks, priority: {plan_res.get('priority_skills', [])[:2]}, eval: {plan_eval['score']}/100")
        for issue in plan_eval["issues"]: print(f"    ⚠ {issue}")

        total_ats     += ats_eval["score"]
        total_scoring += sc_eval["score"]
        total_plan    += plan_eval["score"]

    n = len(TEST_PROFILES)
    print(f"\n{'='*60}")
    print(f"AGGREGATE SCORES (avg across {n} profiles)")
    print(f"  ATS prompt     : {total_ats/n:.0f}/100")
    print(f"  Scoring prompt : {total_scoring/n:.0f}/100")
    print(f"  Plan prompt    : {total_plan/n:.0f}/100")
    print(f"  Overall avg    : {(total_ats+total_scoring+total_plan)/(3*n):.0f}/100")
    print(f"{'='*60}\n")


async def _call(system_prompt, user_prompt, max_tokens=1200, temp=0.2):
    """GPT call with system/user split, matching production usage."""
    res = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=temp,
        max_tokens=max_tokens,
    )
    return json.loads(res.choices[0].message.content)


if __name__ == "__main__":
    asyncio.run(run_eval())
