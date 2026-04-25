from datetime import datetime, timedelta, timezone

import pytest

import auth
import models


async def seed_records_data(db_session):
    owner = models.PhrUser(first_name="Owner", last_name="User", contact_phone="8222000001")
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)

    patient = models.Patient(
        first_name="Owner",
        last_name="User",
        date_of_birth=datetime(1995, 5, 5).date(),
        gender="female",
        local_mrn_value="MRN-2",
        contact_phone=owner.contact_phone,
    )
    organization = models.Organization(organization_name="City Lab", address_line1="Main Street")
    db_session.add_all([patient, organization])
    await db_session.commit()
    await db_session.refresh(patient)
    await db_session.refresh(organization)

    encounter = models.Encounter(patient_id=patient.id, service_provider_id=organization.id)
    practitioner = models.Practitioner(first_name="Asha", last_name="Sharma")
    db_session.add_all([encounter, practitioner])
    await db_session.commit()
    await db_session.refresh(encounter)
    await db_session.refresh(practitioner)

    cbc = models.Test(test_name="CBC", method="Automated")
    lft = models.Test(test_name="LFT", method="Biochemistry")
    db_session.add_all([cbc, lft])
    await db_session.commit()
    await db_session.refresh(cbc)
    await db_session.refresh(lft)

    now = datetime.now(timezone.utc)
    r1 = models.ServiceRequest(
        local_order_value="REC-1",
        order_date=now - timedelta(days=4),
        status="completed",
        patient_id=patient.id,
        requester_id=practitioner.id,
        encounter_id=encounter.id,
    )
    r2 = models.ServiceRequest(
        local_order_value="REC-2",
        order_date=now - timedelta(days=1),
        status="pending",
        patient_id=patient.id,
        requester_id=practitioner.id,
        encounter_id=encounter.id,
    )
    db_session.add_all([r1, r2])
    await db_session.commit()
    await db_session.refresh(r1)
    await db_session.refresh(r2)

    db_session.add_all(
        [
            models.ServiceRequestItem(service_request_id=r1.id, test_id=cbc.id),
            models.ServiceRequestItem(service_request_id=r2.id, test_id=lft.id),
        ]
    )
    await db_session.commit()

    return owner, patient, r1, r2


def build_access_token(user: models.PhrUser):
    return auth.create_access_token(
        {
            "sub": user.contact_phone,
            "user_id": str(user.id),
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip() or "User",
        }
    )


@pytest.mark.asyncio
async def test_records_list_supports_filters_pagination_and_metadata(client, db_session):
    owner, _, _, _ = await seed_records_data(db_session)
    token = build_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(
        "/api/v1/records",
        headers=headers,
        params={
            "status": "completed",
            "search": "CBC",
            "page": 1,
            "page_size": 1,
            "sort_by": "display_id",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["total_pages"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["metadata"]["record_type"] == "lab_report"
    assert payload["items"][0]["metadata"]["source"] == "City Lab"


@pytest.mark.asyncio
async def test_records_by_profile_and_details_flow(client, db_session):
    owner, _, first_record, _ = await seed_records_data(db_session)
    token = build_access_token(owner)
    headers = {"Authorization": f"Bearer {token}"}

    profiles_response = await client.get("/api/v1/profiles", headers=headers)
    assert profiles_response.status_code == 200
    profile_id = profiles_response.json()[0]["id"]

    list_response = await client.get(
        f"/api/v1/records/profile/{profile_id}",
        headers=headers,
        params={"status": "completed", "record_type": "lab_report"},
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["display_id"] == "REC-1"

    detail_response = await client.get(f"/api/v1/records/{first_record.id}", headers=headers)
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["order_details"]["metadata"]["record_type"] == "lab_report"
    assert detail_payload["order_details"]["metadata"]["source"] == "City Lab"
