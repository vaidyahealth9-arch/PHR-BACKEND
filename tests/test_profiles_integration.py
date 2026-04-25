import pytest

import auth
import models


async def create_user(db_session, phone: str, first_name: str = "User", last_name: str = "One"):
    user = models.PhrUser(first_name=first_name, last_name=last_name, contact_phone=phone)
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
async def test_profile_crud_owner_flow(client, db_session):
    owner = await create_user(db_session, "8000000001", "Ranju", "Owner")
    token = build_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    list_response = await client.get("/api/v1/profiles", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1  # auto primary profile

    create_response = await client.post(
        "/api/v1/profiles",
        json={
            "full_name": "Baby Owner",
            "relationship": "child",
            "gender": "female",
            "blood_group": "O+",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    child_profile = create_response.json()
    assert child_profile["relationship"] == "child"

    update_response = await client.put(
        f"/api/v1/profiles/{child_profile['id']}",
        json={"full_name": "Baby Owner Updated"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["full_name"] == "Baby Owner Updated"

    delete_response = await client.delete(f"/api/v1/profiles/{child_profile['id']}", headers=headers)
    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_caregiver_can_view_not_delete(client, db_session):
    owner = await create_user(db_session, "8000000002", "Owner", "User")
    caregiver = await create_user(db_session, "8000000003", "Care", "Giver")

    owner_headers = {"Authorization": f"Bearer {build_access_token(owner)}"}
    caregiver_headers = {"Authorization": f"Bearer {build_access_token(caregiver)}"}

    create_profile_response = await client.post(
        "/api/v1/profiles",
        json={"full_name": "Dependent Profile", "relationship": "child"},
        headers=owner_headers,
    )
    dependent = create_profile_response.json()

    grant_response = await client.post(
        f"/api/v1/profiles/{dependent['id']}/caregivers",
        json={"caregiver_user_phone": caregiver.contact_phone, "can_view": True, "can_edit": False},
        headers=owner_headers,
    )
    assert grant_response.status_code == 201

    caregiver_get = await client.get(f"/api/v1/profiles/{dependent['id']}", headers=caregiver_headers)
    assert caregiver_get.status_code == 200

    caregiver_update = await client.put(
        f"/api/v1/profiles/{dependent['id']}",
        json={"full_name": "Changed by caregiver"},
        headers=caregiver_headers,
    )
    assert caregiver_update.status_code == 403

    caregiver_delete = await client.delete(f"/api/v1/profiles/{dependent['id']}", headers=caregiver_headers)
    assert caregiver_delete.status_code == 403


@pytest.mark.asyncio
async def test_caregiver_edit_permission_allows_update(client, db_session):
    owner = await create_user(db_session, "8000000004", "Owner", "Edit")
    caregiver = await create_user(db_session, "8000000005", "Care", "Editor")

    owner_headers = {"Authorization": f"Bearer {build_access_token(owner)}"}
    caregiver_headers = {"Authorization": f"Bearer {build_access_token(caregiver)}"}

    create_profile_response = await client.post(
        "/api/v1/profiles",
        json={"full_name": "Dependent Edit", "relationship": "parent"},
        headers=owner_headers,
    )
    dependent = create_profile_response.json()

    grant_response = await client.post(
        f"/api/v1/profiles/{dependent['id']}/caregivers",
        json={"caregiver_user_phone": caregiver.contact_phone, "can_view": True, "can_edit": True},
        headers=owner_headers,
    )
    assert grant_response.status_code == 201

    caregiver_update = await client.put(
        f"/api/v1/profiles/{dependent['id']}",
        json={"full_name": "Edited by caregiver"},
        headers=caregiver_headers,
    )
    assert caregiver_update.status_code == 200
    assert caregiver_update.json()["full_name"] == "Edited by caregiver"
