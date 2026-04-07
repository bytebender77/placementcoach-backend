from fastapi import APIRouter, Depends
from app.db.connection import get_db
from app.core.dependencies import get_current_user
import json

router = APIRouter(prefix="/me", tags=["results"])


@router.get("/results")
async def get_dashboard(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Returns the latest analysis + action plan for the dashboard.
    Single endpoint — frontend makes one call to populate everything.
    """
    user_id = str(current_user["id"])

    # Latest analysis
    analysis = await db.fetchrow(
        """
        SELECT id, placement_low, placement_high, placement_label,
               ats_score, ats_strengths, ats_weaknesses, missing_keywords,
               raw_llm_response, created_at
        FROM analyses
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        user_id,
    )

    if not analysis:
        return {"analysis": None, "plan": None}

    analysis_dict = dict(analysis)
    raw = json.loads(analysis_dict.pop("raw_llm_response", "{}"))
    scoring = raw.get("scoring", {})

    # Latest action plan for this analysis
    plan = await db.fetchrow(
        """
        SELECT id, weeks, priority_skills, duration_weeks, created_at
        FROM action_plans
        WHERE analysis_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        str(analysis["id"]),
    )

    plan_dict = None
    if plan:
        plan_dict = dict(plan)
        plan_dict["weeks"] = json.loads(plan_dict["weeks"])

    return {
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "full_name": current_user["full_name"],
        },
        "analysis": {
            **analysis_dict,
            "reasoning": scoring.get("reasoning", ""),
            "top_positive_signals": scoring.get("top_positive_signals", []),
            "top_risk_factors": scoring.get("top_risk_factors", []),
            "one_line_verdict": raw.get("ats", {}).get("one_line_verdict", ""),
            "formatting_issues": raw.get("ats", {}).get("formatting_issues", []),
        },
        "plan": plan_dict,
    }


@router.get("/profile")
async def get_profile(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    profile = await db.fetchrow(
        "SELECT * FROM profiles WHERE user_id = $1",
        str(current_user["id"]),
    )
    return dict(profile) if profile else {}
