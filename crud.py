from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload
import models
import schemas
from datetime import datetime
from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import array_agg
from collections import namedtuple


async def get_user_by_phone(db: Session, phone_number: str):
    result = await db.execute(
        select(models.PhrUser).filter(models.PhrUser.contact_phone == phone_number)
    )
    return result.scalars().first()


async def get_patient_by_phone(db: Session, phone_number: str):
    """Get patient record by phone number"""
    result = await db.execute(
        select(models.Patient).filter(models.Patient.contact_phone == phone_number)
    )
    return result.scalars().first()


async def get_records(
    db: Session,
    patient_id: int,
    search: str | None = None,
    status: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
):
    if db.bind.dialect.name == "postgresql":
        query = (
            select(
                models.ServiceRequest.id,
                models.ServiceRequest.local_order_value,
                models.ServiceRequest.order_date,
                models.Organization.organization_name,
                models.ServiceRequest.status,
                array_agg(models.Test.test_name).label("test_names"),
            )
            .select_from(models.ServiceRequest)
            .join(models.Encounter)
            .join(models.Organization)
            .join(models.ServiceRequestItem)
            .join(models.Test)
            .where(models.ServiceRequest.patient_id == patient_id)
            .group_by(
                models.ServiceRequest.id,
                models.ServiceRequest.local_order_value,
                models.ServiceRequest.order_date,
                models.Organization.organization_name,
                models.ServiceRequest.status,
            )
        )

        if search:
            query = query.where(
                (models.Test.test_name.ilike(f"%{search}%"))
                | (models.ServiceRequest.local_order_value.ilike(f"%{search}%"))
            )

        if status:
            query = query.where(models.ServiceRequest.status == status)

        if from_date:
            query = query.where(models.ServiceRequest.order_date >= from_date)

        if to_date:
            query = query.where(models.ServiceRequest.order_date <= to_date)

        result = await db.execute(query)
        return result.all()

    else:  # Fallback for SQLite
        query = (
            select(
                models.ServiceRequest.id,
                models.ServiceRequest.local_order_value,
                models.ServiceRequest.order_date,
                models.Organization.organization_name,
                models.ServiceRequest.status,
                models.Test.test_name,
            )
            .select_from(models.ServiceRequest)
            .join(models.Encounter, models.Encounter.id == models.ServiceRequest.encounter_id)
            .join(
                models.Organization,
                models.Organization.id == models.Encounter.service_provider_id,
            )
            .join(
                models.ServiceRequestItem,
                models.ServiceRequest.id == models.ServiceRequestItem.service_request_id,
            )
            .join(models.Test, models.Test.id == models.ServiceRequestItem.test_id)
            .where(models.ServiceRequest.patient_id == patient_id)
        )

        if search:
            query = query.where(
                (models.Test.test_name.ilike(f"%{search}%"))
                | (models.ServiceRequest.local_order_value.ilike(f"%{search}%"))
            )

        if status:
            query = query.where(models.ServiceRequest.status == status)

        if from_date:
            query = query.where(models.ServiceRequest.order_date >= from_date)

        if to_date:
            query = query.where(models.ServiceRequest.order_date <= to_date)

        result = await db.execute(query)
        records = result.all()

        # Manual grouping
        grouped_records = {}
        for r in records:
            if r[0] not in grouped_records:
                grouped_records[r[0]] = {
                    "id": r[0],
                    "local_order_value": r[1],
                    "order_date": r[2],
                    "organization_name": r[3],
                    "status": r[4],
                    "test_names": [],
                }
            grouped_records[r[0]]["test_names"].append(r[5])

        RecordRow = namedtuple(
            "RecordRow",
            [
                "id",
                "local_order_value",
                "order_date",
                "organization_name",
                "status",
                "test_names",
            ],
        )
        return [RecordRow(**data) for data in grouped_records.values()]


async def get_record_details(db: Session, record_id: int, patient_id: int):
    query = (
        select(models.ServiceRequest)
        .options(
            selectinload(models.ServiceRequest.patient),
            selectinload(models.ServiceRequest.requester),
            selectinload(models.ServiceRequest.encounter).selectinload(
                models.Encounter.organization
            ),
            selectinload(models.ServiceRequest.items).selectinload(
                models.ServiceRequestItem.test
            ),
            selectinload(models.ServiceRequest.observations).options(
                selectinload(models.Observation.test_analyte).selectinload(
                    models.TestAnalyte.test
                ),
                selectinload(models.Observation.unit),
                selectinload(models.Observation.reference_range),
            ),
        )
        .where(
            and_(
                models.ServiceRequest.id == record_id,
                models.ServiceRequest.patient_id == patient_id,
            )
        )
    )

    result = await db.execute(query)
    service_request = result.scalars().first()

    if not service_request:
        return None

    patient = service_request.patient
    
    # Handle nullable encounter/organization
    organization_name = "Unknown Lab"
    if service_request.encounter and service_request.encounter.organization:
        organization_name = service_request.encounter.organization.organization_name
    
    practitioner = service_request.requester

    order_details = schemas.Record(
        order_id=service_request.id,
        display_id=service_request.local_order_value,
        date=service_request.order_date.isoformat(),
        lab_name=organization_name,
        status=service_request.status,
        test_names=[item.test.test_name for item in service_request.items] if service_request.items else [],
        patient=patient,
        encounter=service_request.encounter,
        requester=practitioner,
    )

    analytes = []
    for obs in service_request.observations or []:
        try:
            result_str = (
                str(obs.value_numeric) if obs.value_numeric is not None else obs.value_string
            )
            status_color = "AMBER"

            if (
                obs.value_numeric is not None
                and obs.reference_range
                and obs.reference_range.low_value is not None
                and obs.reference_range.high_value is not None
            ):
                if (
                    obs.reference_range.low_value
                    <= obs.value_numeric
                    <= obs.reference_range.high_value
                ):
                    status_color = "GREEN"
                else:
                    status_color = "RED"
            elif obs.interpretation_code and "abnormal" in obs.interpretation_code.lower():
                status_color = "AMBER"

            analytes.append(
                schemas.Analyte(
                    name=obs.test_analyte.analyte_name if obs.test_analyte else "Unknown",
                    result=result_str or "",
                    unit=obs.unit.name if obs.unit else "",
                    reference_range=obs.reference_range.text_range
                    if obs.reference_range
                    else "",
                    status_color=status_color,
                    method=obs.test_analyte.test.method if obs.test_analyte and obs.test_analyte.test else "",
                )
            )
        except Exception as e:
            # Skip problematic observations but log the error
            print(f"Error processing observation {obs.id}: {e}")
            continue

    return schemas.RecordDetails(order_details=order_details, analytes=analytes)
