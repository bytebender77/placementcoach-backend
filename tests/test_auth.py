"""
Basic auth tests — run with: pytest tests/test_auth.py -v
Requires a running test DB (set TEST_DATABASE_URL in env).
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_register_and_login():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Register
        r = await client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "testpass123",
            "full_name": "Test Student",
        })
        assert r.status_code == 201
        data = r.json()
        assert "access_token" in data
        assert data["user"]["email"] == "test@example.com"

        # Login
        r = await client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "testpass123",
        })
        assert r.status_code == 200
        assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_login_wrong_password():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword",
        })
        assert r.status_code == 401
