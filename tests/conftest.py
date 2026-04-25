from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import models
from main import app, auth_lifecycle, get_db


SQLALCHEMY_TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_auth.db"

engine = create_async_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as db:
        yield db


@pytest_asyncio.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    auth_lifecycle.reset()
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    yield

    app.dependency_overrides.clear()
    auth_lifecycle.reset()
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as db:
        yield db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def authenticated_user(client: AsyncClient, db_session: AsyncSession) -> dict:
    """Create an authenticated user with valid token and profile."""
    # Use test phone that returns fixed OTP "123456" in development mode
    phone = "9800122899"
    
    # Create user
    user = models.PhrUser(
        first_name="Test",
        last_name="User",
        contact_phone=phone,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Create profile
    profile = models.Profile(
        owner_user_id=user.id,
        full_name="Test User",
        relationship_type="self",
        blood_group="O+",
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    
    # Send OTP (returns fixed OTP "123456" for this test phone in development)
    await client.post("/api/v1/auth/send-otp", json={"phone_number": phone})
    
    # Verify OTP with the fixed test OTP
    verify_response = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp": "123456"},
    )
    token_data = verify_response.json()
    access_token = token_data["access_token"]
    
    return {
        "user_id": user.id,
        "profile_id": profile.id,
        "phone": phone,
        "access_token": access_token,
        "headers": {"Authorization": f"Bearer {access_token}"},
    }
