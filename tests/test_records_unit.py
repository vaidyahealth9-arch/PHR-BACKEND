from datetime import datetime, timedelta, timezone

import pytest

import crud
import models


async def seed_patient_records(db_session, patient_phone: str = "8111000001"):
    patient = models.Patient(
        first_name="Pat",
        last_name="One",
        date_of_birth=datetime(1990, 1, 1).date(),
        gender="male",
        local_mrn_value="MRN-1",
        contact_phone=patient_phone,
    )
    org1 = models.Organization(organization_name="City Lab", address_line1="Addr 1")
    org2 = models.Organization(organization_name="Metro Diagnostics", address_line1="Addr 2")

    db_session.add_all([patient, org1, org2])
    await db_session.commit()
    await db_session.refresh(patient)
    await db_session.refresh(org1)
    await db_session.refresh(org2)

    encounter1 = models.Encounter(patient_id=patient.id, service_provider_id=org1.id)
    encounter2 = models.Encounter(patient_id=patient.id, service_provider_id=org2.id)
    db_session.add_all([encounter1, encounter2])
    await db_session.commit()
    await db_session.refresh(encounter1)
    await db_session.refresh(encounter2)

    cbc = models.Test(test_name="CBC", method="Automated")
    tsh = models.Test(test_name="TSH", method="Immuno")
    glucose = models.Test(test_name="Glucose", method="Biochemistry")
    db_session.add_all([cbc, tsh, glucose])
    await db_session.commit()
    await db_session.refresh(cbc)
    await db_session.refresh(tsh)
    await db_session.refresh(glucose)

    now = datetime.now(timezone.utc)
    sr1 = models.ServiceRequest(
        local_order_value="ORD-100",
        order_date=now - timedelta(days=5),
        status="completed",
        patient_id=patient.id,
        encounter_id=encounter1.id,
    )
    sr2 = models.ServiceRequest(
        local_order_value="ORD-200",
        order_date=now - timedelta(days=2),
        status="pending",
        patient_id=patient.id,
        encounter_id=encounter2.id,
    )
    sr3 = models.ServiceRequest(
        local_order_value="ORD-300",
        order_date=now - timedelta(days=1),
        status="completed",
        patient_id=patient.id,
        encounter_id=encounter1.id,
    )
    db_session.add_all([sr1, sr2, sr3])
    await db_session.commit()
    await db_session.refresh(sr1)
    await db_session.refresh(sr2)
    await db_session.refresh(sr3)

    db_session.add_all(
        [
            models.ServiceRequestItem(service_request_id=sr1.id, test_id=cbc.id),
            models.ServiceRequestItem(service_request_id=sr2.id, test_id=tsh.id),
            models.ServiceRequestItem(service_request_id=sr3.id, test_id=glucose.id),
        ]
    )
    await db_session.commit()

    return patient


@pytest.mark.asyncio
async def test_get_records_filters_sorts_and_paginates(db_session):
    patient = await seed_patient_records(db_session)

    records, total = await crud.get_records(
        db_session,
        patient_id=patient.id,
        status="completed",
        source="city",
        sort_by="display_id",
        sort_order="asc",
        page=1,
        page_size=1,
    )

    assert total == 2
    assert len(records) == 1
    assert records[0].local_order_value == "ORD-100"
    assert records[0].record_type == "lab_report"


@pytest.mark.asyncio
async def test_get_records_search_and_record_type_filter(db_session):
    patient = await seed_patient_records(db_session)

    records, total = await crud.get_records(
        db_session,
        patient_id=patient.id,
        search="glucose",
        record_type="lab_report",
        sort_by="date",
        sort_order="desc",
    )
    assert total == 1
    assert len(records) == 1
    assert records[0].local_order_value == "ORD-300"

    none_records, none_total = await crud.get_records(
        db_session,
        patient_id=patient.id,
        record_type="radiology",
    )
    assert none_total == 0
    assert none_records == []
