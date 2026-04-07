import json
import asyncio
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.scoring_service import compute_base_score
from app.prompts.ats_prompt import build_ats_prompt, SYSTEM_PROMPT as ATS_SYSTEM
from app.prompts.scoring_prompt import build_scoring_prompt, SYSTEM_PROMPT as SCORING_SYSTEM
from app.prompts.plan_prompt import build_plan_prompt, SYSTEM_PROMPT as PLAN_SYSTEM

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


# ─── Per-prompt GPT settings ─────────────────────────────────────────────────
# Each prompt has its own temperature and max_tokens, tuned for its purpose:
#   ATS      → low temp (0.2)  for consistent, reliable scoring
#   Scoring  → medium-low (0.3) for slight reasoning variation
#   Plan     → medium (0.5) for creative, personalised plans

PROMPT_SETTINGS = {
    "ats":     {"temperature": 0.2, "max_tokens": 1200},
    "scoring": {"temperature": 0.3, "max_tokens": 1000},
    "plan":    {"temperature": 0.5, "max_tokens": 2000},
}


async def _call_gpt(
    system_prompt: str,
    user_prompt: str,
    prompt_type: str = "ats",
) -> dict:
    """Single GPT call with system/user message split and per-prompt settings."""
    cfg = PROMPT_SETTINGS.get(prompt_type, PROMPT_SETTINGS["ats"])
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
    )
    raw = response.choices[0].message.content
    return json.loads(raw)


async def run_analysis(
    resume_text: str,
    cgpa: float,
    skills: list,
    college_tier: str,
    year: str,
    target_roles: list,
    target_companies: list,
    co_curricular: list,
    achievements: list,
    certifications: list,
    github_url: str,
    linkedin_url: str,
    open_to_remote: bool,
    preferred_locations: list,
    user_id: str,
    resume_id: str,
    db,
) -> dict:
    """
    Full analysis pipeline:
    1. Rule-based pre-score (sync, free)
    2. ATS prompt + placement scoring prompt run in PARALLEL (saves ~2s)
    3. Save to DB
    4. Return structured result
    """

    # Step 1: Rule-based baseline
    base_score = compute_base_score(cgpa, skills, college_tier, year)

    # Step 2: Parallel GPT calls (ATS + placement scoring)
    ats_user_prompt = build_ats_prompt(resume_text, target_roles, target_companies)
    scoring_user_prompt = build_scoring_prompt(
        resume_text, cgpa, skills, college_tier, year,
        target_roles, target_companies, co_curricular,
        achievements, certifications, base_score
    )

    ats_result, scoring_result = await asyncio.gather(
        _call_gpt(ATS_SYSTEM, ats_user_prompt, "ats"),
        _call_gpt(SCORING_SYSTEM, scoring_user_prompt, "scoring"),
    )

    # Step 3: Upsert profile
    profile_row = await db.fetchrow(
        """
        INSERT INTO profiles (
            user_id, cgpa, college_tier, year, skills, target_roles, target_companies,
            co_curricular, achievements, certifications, github_url, linkedin_url,
            open_to_remote, preferred_locations
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (user_id) DO UPDATE SET
            cgpa = EXCLUDED.cgpa,
            college_tier = EXCLUDED.college_tier,
            year = EXCLUDED.year,
            skills = EXCLUDED.skills,
            target_roles = EXCLUDED.target_roles,
            target_companies = EXCLUDED.target_companies,
            co_curricular = EXCLUDED.co_curricular,
            achievements = EXCLUDED.achievements,
            certifications = EXCLUDED.certifications,
            github_url = EXCLUDED.github_url,
            linkedin_url = EXCLUDED.linkedin_url,
            open_to_remote = EXCLUDED.open_to_remote,
            preferred_locations = EXCLUDED.preferred_locations,
            updated_at = NOW()
        RETURNING id
        """,
        user_id, cgpa, college_tier, year,
        skills, target_roles, target_companies,
        co_curricular, achievements, certifications,
        github_url, linkedin_url, open_to_remote, preferred_locations,
    )

    # Step 4: Save analysis
    raw_response = {"ats": ats_result, "scoring": scoring_result}

    analysis_row = await db.fetchrow(
        """
        INSERT INTO analyses (
            user_id, resume_id, profile_id,
            placement_low, placement_high, placement_label,
            ats_score, ats_strengths, ats_weaknesses, missing_keywords,
            raw_llm_response
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        RETURNING id, created_at
        """,
        user_id,
        resume_id,
        str(profile_row["id"]),
        scoring_result.get("placement_low", base_score["placement_low"]),
        scoring_result.get("placement_high", base_score["placement_high"]),
        scoring_result.get("label", base_score["label"]),
        ats_result.get("ats_score", 50),
        ats_result.get("strengths", []),
        ats_result.get("weaknesses", []),
        ats_result.get("missing_keywords", []),
        json.dumps(raw_response),
    )

    return {
        "id": str(analysis_row["id"]),
        "created_at": analysis_row["created_at"],
        "placement": {
            "low": scoring_result.get("placement_low", base_score["placement_low"]),
            "high": scoring_result.get("placement_high", base_score["placement_high"]),
            "label": scoring_result.get("label", base_score["label"]),
            "reasoning": scoring_result.get("reasoning", ""),
            "top_positive_signals": scoring_result.get("top_positive_signals", []),
            "top_risk_factors": scoring_result.get("top_risk_factors", []),
            # New: company fit + fastest improvement from production scoring prompt
            "company_fit": scoring_result.get("company_fit", {}),
            "fastest_improvement": scoring_result.get("fastest_improvement", ""),
        },
        "ats": {
            "score": ats_result.get("ats_score", 50),
            # New: dimension-level breakdown from production ATS prompt
            "dimension_scores": ats_result.get("dimension_scores", {}),
            "strengths": ats_result.get("strengths", []),
            "weaknesses": ats_result.get("weaknesses", []),
            "missing_keywords": ats_result.get("missing_keywords", []),
            "formatting_issues": ats_result.get("formatting_issues", []),
            # New: India-specific red flags
            "india_red_flags_found": ats_result.get("india_red_flags_found", []),
            "one_line_verdict": ats_result.get("one_line_verdict", ""),
        },
    }


async def generate_plan(analysis_id: str, user_id: str, db) -> dict:
    """Generate 6-week action plan based on analysis."""

    # Fetch analysis + profile
    row = await db.fetchrow(
        """
        SELECT a.*, p.cgpa, p.college_tier, p.year, p.skills, p.target_roles
        FROM analyses a
        JOIN profiles p ON p.user_id = a.user_id
        WHERE a.id = $1 AND a.user_id = $2
        """,
        analysis_id, user_id,
    )

    if not row:
        raise ValueError("Analysis not found or unauthorized")

    # Extract the full scoring + ats results from the stored LLM response
    raw_llm = json.loads(row["raw_llm_response"])
    scoring_data = raw_llm.get("scoring", {})
    ats_data = raw_llm.get("ats", {})

    prompt = build_plan_prompt(
        cgpa=row["cgpa"],
        skills=row["skills"],
        college_tier=row["college_tier"],
        year=row["year"],
        target_roles=row["target_roles"],
        ats_weaknesses=row["ats_weaknesses"],
        missing_keywords=row["missing_keywords"],
        placement_label=row["placement_label"],
        placement_reasoning=scoring_data.get("reasoning", ""),
        # New: pass formatting issues and company fit to the plan prompt
        formatting_issues=ats_data.get("formatting_issues", []),
        company_fit=scoring_data.get("company_fit"),
    )

    plan_result = await _call_gpt(PLAN_SYSTEM, prompt, "plan")

    plan_row = await db.fetchrow(
        """
        INSERT INTO action_plans (user_id, analysis_id, weeks, priority_skills, duration_weeks)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, created_at
        """,
        user_id,
        analysis_id,
        json.dumps(plan_result.get("weeks", [])),
        plan_result.get("priority_skills", []),
        plan_result.get("duration_weeks", 6),
    )

    return {
        "id": str(plan_row["id"]),
        "created_at": plan_row["created_at"],
        "weeks": plan_result.get("weeks", []),
        "priority_skills": plan_result.get("priority_skills", []),
        "duration_weeks": plan_result.get("duration_weeks", 6),
        "motivational_note": plan_result.get("motivational_note", ""),
    }
