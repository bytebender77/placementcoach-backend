from fastapi import APIRouter, Depends
from app.db.connection import get_db
from app.models.user import UserCreate, UserLogin, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: UserCreate, db=Depends(get_db)):
    result = await auth_service.register_user(data, db)
    return TokenResponse(
        access_token=result["token"],
        user=result["user"],
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db=Depends(get_db)):
    result = await auth_service.login_user(data, db)
    return TokenResponse(
        access_token=result["token"],
        user=result["user"],
    )
