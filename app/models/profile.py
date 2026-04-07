from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid


class ProfileCreate(BaseModel):
    cgpa: float = Field(..., ge=0.0, le=10.0)
    college_tier: Literal["tier1", "tier2", "tier3"]
    year: Literal["2nd", "3rd", "4th", "fresher"]
    skills: List[str] = Field(..., min_length=1)
    target_roles: List[str] = []
    target_companies: List[str] = []


class ProfileOut(ProfileCreate):
    id: uuid.UUID
    user_id: uuid.UUID
