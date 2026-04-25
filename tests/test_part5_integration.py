import io

import pytest

import auth
import models


async def create_user(db_session, phone: str):
    user = models.PhrUser(first_name="Upload", last_name="User", contact_phone=phone)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def build_access_token(user: models.PhrUser):
    return auth.create_access_token(
        {
            "sub": user.contact_phone,
            "user_id": str(user.id),
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip() or "User",
        }
    )


@pytest.mark.asyncio
async def test_upload_extract_and_confirm_ocr_flow(client, db_session):
    user = await create_user(db_session, "8333000001")
    token = build_access_token(user)
    headers = {"Authorization": f"Bearer {token}"}

    profiles_response = await client.get("/api/v1/profiles", headers=headers)
    assert profiles_response.status_code == 200
    profile_id = profiles_response.json()[0]["id"]

    files = {
        "file": ("cbc-report.pdf", io.BytesIO(b"fake-pdf-content"), "application/pdf"),
    }
    data = {
        "profile_id": str(profile_id),
        "record_type": "lab_report",
        "title": "CBC Report",
        "source_facility": "City Lab",
    }

    upload_response = await client.post(
        "/api/v1/records/upload",
        headers=headers,
        data=data,
        files=files,
    )
    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    assert upload_payload["upload_status"] == "uploaded"
    record_id = upload_payload["record_id"]

    extract_response = await client.post(f"/api/v1/ocr/extract/{record_id}", headers=headers)
    assert extract_response.status_code == 200
    extract_payload = extract_response.json()
    assert extract_payload["status"] == "completed"
    assert extract_payload["record_id"] == record_id
    assert "CBC" in extract_payload["extracted_tags"]

    status_response = await client.get(f"/api/v1/ocr/{record_id}", headers=headers)
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    confirm_response = await client.post(
        f"/api/v1/ocr/{record_id}/confirm",
        headers=headers,
        json={
            "title": "CBC Confirmed",
            "record_type": "lab_report",
            "confirmed_tags": ["CBC", "General"],
        },
    )
    assert confirm_response.status_code == 200
    confirm_payload = confirm_response.json()
    assert confirm_payload["is_confirmed"] is True
    assert "General" in confirm_payload["confirmed_tags"]


@pytest.mark.asyncio
async def test_uploaded_record_is_visible_in_profile_records_list(client, db_session):
    user = await create_user(db_session, "8333000003")
    token = build_access_token(user)
    headers = {"Authorization": f"Bearer {token}"}

    profiles_response = await client.get("/api/v1/profiles", headers=headers)
    assert profiles_response.status_code == 200
    profile_id = profiles_response.json()[0]["id"]

    files = {
        "file": ("uploaded-visible.pdf", io.BytesIO(b"fake-pdf-content"), "application/pdf"),
    }
    data = {
        "profile_id": str(profile_id),
        "record_type": "lab_report",
        "title": "Uploaded Visible",
        "source_facility": "Upload Lab",
    }

    upload_response = await client.post(
        "/api/v1/records/upload",
        headers=headers,
        data=data,
        files=files,
    )
    assert upload_response.status_code == 200

    list_response = await client.get(
        f"/api/v1/records/profile/{profile_id}",
        headers=headers,
        params={"record_type": "lab_report"},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] >= 1
    assert any(item["display_id"].startswith("UPL-") for item in payload["items"])


@pytest.mark.asyncio
async def test_upload_rejects_invalid_file_type(client, db_session):
    user = await create_user(db_session, "8333000002")
    token = build_access_token(user)
    headers = {"Authorization": f"Bearer {token}"}

    profiles_response = await client.get("/api/v1/profiles", headers=headers)
    profile_id = profiles_response.json()[0]["id"]

    files = {
        "file": ("malware.exe", io.BytesIO(b"x"), "application/x-msdownload"),
    }
    data = {
        "profile_id": str(profile_id),
        "record_type": "other",
        "title": "Invalid Upload",
    }

    response = await client.post(
        "/api/v1/records/upload",
        headers=headers,
        data=data,
        files=files,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_TYPE"
