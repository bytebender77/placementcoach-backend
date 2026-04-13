from fastapi import HTTPException, status

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import UserCreate, UserLogin


async def register_user(data: UserCreate, db) -> dict:
    existing = await db.fetchrow("SELECT id FROM users WHERE email = $1", data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )

    hashed = hash_password(data.password)
    row = await db.fetchrow(
        """
        INSERT INTO users (email, password_hash, full_name)
        VALUES ($1, $2, $3)
        RETURNING id, email, full_name, created_at
        """,
        data.email, hashed, data.full_name,
    )

    # Provision free plan for the new user
    from app.services.subscription_service import provision_free_plan
    await provision_free_plan(str(row["id"]), db)

    token = create_access_token(str(row["id"]), row["email"])
    return {"token": token, "user": dict(row)}


async def login_user(data: UserLogin, db) -> dict:
    row = await db.fetchrow(
        "SELECT id, email, full_name, password_hash, created_at FROM users WHERE email = $1",
        data.email,
    )

    if not row or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token(str(row["id"]), row["email"])
    user = {k: v for k, v in dict(row).items() if k != "password_hash"}
    return {"token": token, "user": user}
