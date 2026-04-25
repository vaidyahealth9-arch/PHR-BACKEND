from datetime import datetime, timedelta, timezone

import pytest

import models
from main import auth_lifecycle


async def create_user(db_session, phone: str):
    user = models.PhrUser(
        first_name="Test",
        last_name="User",
        contact_phone=phone,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_send_verify_and_me_flow(client, db_session):
    phone = "9800122899"
    await create_user(db_session, phone)

    send_response = await client.post("/api/v1/auth/send-otp", json={"phone_number": phone})
    assert send_response.status_code == 200

    verify_response = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp": "123456"},
    )
    assert verify_response.status_code == 200

    token_payload = verify_response.json()
    assert token_payload["token_type"] == "bearer"
    assert token_payload["access_token"]
    assert token_payload["refresh_token"]

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_payload['access_token']}"},
    )
    assert me_response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_otp_locks_after_max_attempts(client, db_session):
    phone = "9000000001"
    await create_user(db_session, phone)

    await client.post("/api/v1/auth/send-otp", json={"phone_number": phone})

    for attempt in range(1, 6):
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone, "otp": "000000"},
        )
        if attempt < 5:
            assert response.status_code == 400
        else:
            assert response.status_code == 429
            assert response.json()["error"]["code"] == "OTP_VERIFICATION_LOCKED"


@pytest.mark.asyncio
async def test_expired_otp_rejected(client, db_session):
    phone = "9000000002"
    await create_user(db_session, phone)

    await client.post("/api/v1/auth/send-otp", json={"phone_number": phone})

    auth_lifecycle.otp_records[phone].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    response = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp": "000000"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_EXPIRED"


@pytest.mark.asyncio
async def test_refresh_token_rotation(client, db_session):
    phone = "9800122899"
    await create_user(db_session, phone)

    await client.post("/api/v1/auth/send-otp", json={"phone_number": phone})
    verify_response = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp": "123456"},
    )
    payload = verify_response.json()

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": payload["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    new_payload = refresh_response.json()
    assert new_payload["refresh_token"] != payload["refresh_token"]

    reused_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": payload["refresh_token"]},
    )
    assert reused_response.status_code == 401
    assert reused_response.json()["error"]["code"] == "TOKEN_REVOKED"


@pytest.mark.asyncio
async def test_logout_revokes_access_and_refresh_tokens(client, db_session):
    phone = "9800122899"
    await create_user(db_session, phone)

    await client.post("/api/v1/auth/send-otp", json={"phone_number": phone})
    verify_response = await client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone, "otp": "123456"},
    )
    payload = verify_response.json()

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": payload["refresh_token"]},
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert logout_response.status_code == 200

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert me_response.status_code == 401

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": payload["refresh_token"]},
    )
    assert refresh_response.status_code == 401
