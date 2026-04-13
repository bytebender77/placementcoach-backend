from fastapi import APIRouter, Depends, HTTPException, status
from app.db.connection import get_db
from app.core.dependencies import get_current_user
from app.services import opportunity_service, career_path_service
from app.middleware.quota_middleware import require_opportunities_feature, require_career_path_feature
import json

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.post("/find")
async def find_opportunities(
    data: dict,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
    _gate=Depends(require_opportunities_feature),
):
    """
    Fetch real internship/job opportunities for this student.
    Uses GPT web search → falls back to curated platform links.
    Requires analysis_id from a completed analysis.
    """
    user_id     = str(current_user["id"])
    analysis_id = data.get("analysis_id")

    if not analysis_id:
        raise HTTPException(status_code=400, detail="analysis_id required")

    # Fetch profile + analysis from DB
    profile = await db.fetchrow(
        "SELECT * FROM profiles WHERE user_id = $1", user_id
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Complete your profile first.")

    profile_dict = dict(profile)

    result = await opportunity_service.fetch_opportunities(
        cgpa              = float(profile_dict.get("cgpa", 7.0)),
        skills            = profile_dict.get("skills", []),
        college_tier      = profile_dict.get("college_tier", "tier2"),
        year              = profile_dict.get("year", "4th"),
        target_roles      = profile_dict.get("target_roles", []),
        target_companies  = profile_dict.get("target_companies", []),
        co_curricular     = profile_dict.get("co_curricular", []),
        certifications    = profile_dict.get("certifications", []),
        open_to_remote    = profile_dict.get("open_to_remote", True),
        preferred_locations = profile_dict.get("preferred_locations", []),
        placement_label   = data.get("placement_label", "Moderate"),
        user_id           = user_id,
        analysis_id       = analysis_id,
        db                = db,
    )
    return result


@router.get("/my")
async def get_my_opportunities(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get all opportunities fetched for this user, most recent first."""
    user_id = str(current_user["id"])
    rows = await db.fetch(
        """
        SELECT * FROM opportunities
        WHERE user_id = $1
        ORDER BY match_score DESC, fetched_at DESC
        LIMIT 20
        """,
        user_id,
    )
    return [dict(r) for r in rows]


@router.post("/save/{opportunity_id}")
async def save_opportunity(
    opportunity_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await opportunity_service.save_opportunity(
        str(current_user["id"]), opportunity_id, db
    )
    return result


@router.post("/applied/{opportunity_id}")
async def mark_applied(
    opportunity_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await opportunity_service.mark_applied(
        str(current_user["id"]), opportunity_id, db
    )
    return result


@router.get("/saved")
async def get_saved(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    return await opportunity_service.get_saved_opportunities(
        str(current_user["id"]), db
    )


# ── Career Path Routes ────────────────────────────────────────────────────

@router.post("/career-path")
async def generate_career_path(
    data: dict,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
    _gate=Depends(require_career_path_feature),
):
    """
    Generate full career path analysis:
    - Reality check on target companies
    - Co-curricular activity insights  
    - Alternative career paths
    - Personalised motivation
    """
    user_id     = str(current_user["id"])
    analysis_id = data.get("analysis_id")

    if not analysis_id:
        raise HTTPException(status_code=400, detail="analysis_id required")

    profile = await db.fetchrow(
        "SELECT * FROM profiles WHERE user_id = $1", user_id
    )
    analysis = await db.fetchrow(
        "SELECT * FROM analyses WHERE id = $1 AND user_id = $2",
        analysis_id, user_id
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    result = await career_path_service.generate_career_paths(
        user_id=user_id,
        analysis_id=analysis_id,
        profile=dict(profile),
        analysis=dict(analysis),
        db=db,
    )
    return result


@router.get("/career-path/latest")
async def get_career_path(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await career_path_service.get_latest_career_path(
        str(current_user["id"]), db
    )
    if not result:
        raise HTTPException(status_code=404, detail="No career path generated yet")
    return result
