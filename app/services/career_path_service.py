import json
from openai import AsyncOpenAI
from app.core.config import settings
from app.prompts.career_path_prompt import build_career_path_prompt

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def generate_career_paths(
    user_id: str,
    analysis_id: str,
    profile: dict,
    analysis: dict,
    db,
) -> dict:
    """
    Generates:
      - Reality check on target companies
      - Co-curricular activity analysis
      - Primary path assessment
      - 2-3 alternative career paths
      - Personalised motivation
    """

    prompt = build_career_path_prompt(
        cgpa             = profile.get("cgpa", 7.0),
        skills           = profile.get("skills", []),
        college_tier     = profile.get("college_tier", "tier2"),
        year             = profile.get("year", "4th"),
        target_roles     = profile.get("target_roles", []),
        target_companies = profile.get("target_companies", []),
        co_curricular    = profile.get("co_curricular", []),
        achievements     = profile.get("achievements", []),
        certifications   = profile.get("certifications", []),
        placement_label  = analysis.get("placement_label", "Moderate"),
        ats_score        = analysis.get("ats_score", 50),
        placement_low    = analysis.get("placement_low", 30),
        placement_high   = analysis.get("placement_high", 55),
        ats_weaknesses   = analysis.get("ats_weaknesses", []),
        missing_keywords = analysis.get("missing_keywords", []),
        company_fit      = json.loads(analysis.get("raw_llm_response", "{}"))
                              .get("scoring", {}).get("company_fit"),
    )

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.5,
        max_tokens=2500,
    )

    result = json.loads(response.choices[0].message.content)

    # Persist to DB
    row = await db.fetchrow(
        """
        INSERT INTO career_paths (
            user_id, analysis_id, primary_path, alternate_paths,
            co_curricular_insights, motivation_note, reality_check
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, created_at
        """,
        user_id,
        analysis_id,
        json.dumps(result.get("primary_path", {})),
        json.dumps(result.get("alternate_paths", [])),
        json.dumps(result.get("co_curricular_insights", {})),
        result.get("motivation", {}).get("body", ""),
        result.get("reality_check", {}).get("honest_assessment", ""),
    )

    return {
        "id": str(row["id"]),
        "created_at": row["created_at"],
        **result,
    }


async def get_latest_career_path(user_id: str, db) -> dict:
    row = await db.fetchrow(
        """
        SELECT id, primary_path, alternate_paths, co_curricular_insights,
               motivation_note, reality_check, created_at
        FROM career_paths
        WHERE user_id = $1
        ORDER BY created_at DESC LIMIT 1
        """,
        user_id,
    )
    if not row:
        return {}
    d = dict(row)
    for key in ("primary_path", "alternate_paths", "co_curricular_insights"):
        if d.get(key):
            d[key] = json.loads(d[key]) if isinstance(d[key], str) else d[key]
    return d
