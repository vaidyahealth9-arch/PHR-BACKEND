from datetime import date, datetime, timezone

from sqlalchemy import select

import models
from database import SessionLocal, engine


SEED_PHONE = "9800122899"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def init_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


async def seed_data() -> None:
    async with SessionLocal() as db:
        now = _now()

        # Core identity: user + linked clinical patient.
        user_result = await db.execute(select(models.PhrUser).where(models.PhrUser.contact_phone == SEED_PHONE))
        user = user_result.scalars().first()
        if not user:
            user = models.PhrUser(
                first_name="Ranju",
                last_name="User",
                gender="M",
                date_of_birth=date(1993, 5, 12),
                contact_phone=SEED_PHONE,
                contact_email="ranju@example.com",
                city="Bangalore",
                state="Karnataka",
                country="India",
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            await db.flush()

        patient_result = await db.execute(select(models.Patient).where(models.Patient.contact_phone == SEED_PHONE))
        patient = patient_result.scalars().first()
        if not patient:
            patient = models.Patient(
                first_name="Ranju",
                last_name="User",
                middle_name="",
                date_of_birth=date(1993, 5, 12),
                gender="Male",
                local_mrn_value="MRN-9800122899",
                contact_phone=SEED_PHONE,
                contact_email="ranju@example.com",
            )
            db.add(patient)
            await db.flush()

        # Ensure primary profile for MVP profile/records flows.
        primary_profile_result = await db.execute(
            select(models.Profile).where(
                models.Profile.owner_user_id == user.id,
                models.Profile.is_primary == True,
            )
        )
        primary_profile = primary_profile_result.scalars().first()
        if not primary_profile:
            primary_profile = models.Profile(
                owner_user_id=user.id,
                full_name="Ranju User",
                relationship_type="self",
                date_of_birth=date(1993, 5, 12),
                gender="male",
                blood_group="B+",
                is_primary=True,
                created_at=now,
                updated_at=now,
            )
            db.add(primary_profile)
            await db.flush()

        # Legacy lab-report path seed (used by /records and record details).
        org_result = await db.execute(select(models.Organization).where(models.Organization.organization_name == "Vaidya Diagnostics"))
        org = org_result.scalars().first()
        if not org:
            org = models.Organization(organization_name="Vaidya Diagnostics", address_line1="Bangalore")
            db.add(org)
            await db.flush()

        practitioner_result = await db.execute(select(models.Practitioner).where(models.Practitioner.mci_reg_no == "MCI123456"))
        practitioner = practitioner_result.scalars().first()
        if not practitioner:
            practitioner = models.Practitioner(
                first_name="Meera",
                last_name="Sharma",
                middle_name="",
                prefix="Dr.",
                mci_reg_no="MCI123456",
            )
            db.add(practitioner)
            await db.flush()

        encounter_result = await db.execute(
            select(models.Encounter).where(
                models.Encounter.patient_id == patient.id,
                models.Encounter.service_provider_id == org.id,
            )
        )
        encounter = encounter_result.scalars().first()
        if not encounter:
            encounter = models.Encounter(patient_id=patient.id, service_provider_id=org.id)
            db.add(encounter)
            await db.flush()

        service_request_result = await db.execute(
            select(models.ServiceRequest).where(models.ServiceRequest.local_order_value == "ORD-1001")
        )
        service_request = service_request_result.scalars().first()
        if not service_request:
            service_request = models.ServiceRequest(
                local_order_value="ORD-1001",
                order_date=now,
                status="completed",
                patient_id=patient.id,
                requester_id=practitioner.id,
                encounter_id=encounter.id,
            )
            db.add(service_request)
            await db.flush()

        test_result = await db.execute(select(models.Test).where(models.Test.test_name == "Complete Blood Count"))
        test = test_result.scalars().first()
        if not test:
            test = models.Test(test_name="Complete Blood Count", method="Automated Hematology Analyzer")
            db.add(test)
            await db.flush()

        sri_result = await db.execute(
            select(models.ServiceRequestItem).where(
                models.ServiceRequestItem.service_request_id == service_request.id,
                models.ServiceRequestItem.test_id == test.id,
            )
        )
        if not sri_result.scalars().first():
            db.add(models.ServiceRequestItem(service_request_id=service_request.id, test_id=test.id))

        analyte_result = await db.execute(select(models.TestAnalyte).where(models.TestAnalyte.analyte_name == "Hemoglobin"))
        analyte = analyte_result.scalars().first()
        if not analyte:
            analyte = models.TestAnalyte(analyte_name="Hemoglobin", test_id=test.id)
            db.add(analyte)
            await db.flush()

        unit_result = await db.execute(select(models.Unit).where(models.Unit.name == "g/dL"))
        unit = unit_result.scalars().first()
        if not unit:
            unit = models.Unit(name="g/dL")
            db.add(unit)
            await db.flush()

        rr_result = await db.execute(select(models.ReferenceRange).where(models.ReferenceRange.text_range == "13.0 - 17.0"))
        reference_range = rr_result.scalars().first()
        if not reference_range:
            reference_range = models.ReferenceRange(text_range="13.0 - 17.0", low_value=13, high_value=17)
            db.add(reference_range)
            await db.flush()

        obs_result = await db.execute(
            select(models.Observation).where(
                models.Observation.service_request_id == service_request.id,
                models.Observation.analyte_id == analyte.id,
            )
        )
        if not obs_result.scalars().first():
            db.add(
                models.Observation(
                    service_request_id=service_request.id,
                    analyte_id=analyte.id,
                    value_numeric=14.2,
                    value_string=None,
                    unit_id=unit.id,
                    reference_range_id=reference_range.id,
                    interpretation_code="normal",
                )
            )

        # Uploaded/OCR path seed (used by record upload-summary-trend-share UI)
        uploaded_result = await db.execute(
            select(models.UploadedRecord).where(
                models.UploadedRecord.profile_id == primary_profile.id,
                models.UploadedRecord.file_name == "sample-lipid-panel.pdf",
            )
        )
        uploaded = uploaded_result.scalars().first()
        if not uploaded:
            uploaded = models.UploadedRecord(
                profile_id=primary_profile.id,
                owner_user_id=user.id,
                record_type="lab_report",
                title="Lipid Panel",
                description="Sample uploaded report",
                issued_date=date.today(),
                source_facility="Vaidya Diagnostics",
                source_doctor="Dr. Meera Sharma",
                file_name="sample-lipid-panel.pdf",
                file_path="seed/sample-lipid-panel.pdf",
                mime_type="application/pdf",
                file_size_bytes=102400,
                upload_status="tags_confirmed",
                created_at=now,
                updated_at=now,
            )
            db.add(uploaded)
            await db.flush()

        ocr_result = await db.execute(select(models.OCRExtraction).where(models.OCRExtraction.record_id == uploaded.id))
        if not ocr_result.scalars().first():
            db.add(
                models.OCRExtraction(
                    record_id=uploaded.id,
                    status="completed",
                    extracted_record_type="lab_report",
                    extracted_title="Lipid Panel",
                    extracted_issued_date=date.today(),
                    extracted_source_facility="Vaidya Diagnostics",
                    extracted_source_doctor="Dr. Meera Sharma",
                    extracted_tags="cholesterol,ldl,hdl,triglycerides",
                    confidence=0.93,
                    raw_text="Seed OCR text for lipid panel",
                    is_confirmed=True,
                    confirmed_tags="cholesterol,ldl,hdl,triglycerides",
                    created_at=now,
                    updated_at=now,
                )
            )

        await db.commit()
        print("MVP seed data ensured successfully.")


async def main() -> None:
    await init_schema()
    await seed_data()


if __name__ == "__main__":
    import asyncio

    async def run_multiple_seeds():
        # First seed the default user
        await main()
        
        # Then seed the test user 1231231231
        print("\nSeeding additional test user 1231231231...")
        import os
        from database import SessionLocal
        import models
        from sqlalchemy import select
        async with SessionLocal() as db:
            phone = "1231231231"
            now = _now()
            
            # Create User
            user_res = await db.execute(select(models.PhrUser).where(models.PhrUser.contact_phone == phone))
            user = user_res.scalars().first()
            if not user:
                user = models.PhrUser(
                    first_name="Test",
                    last_name="User",
                    contact_phone=phone,
                    created_at=now,
                    updated_at=now
                )
                db.add(user)
                await db.flush()
                print(f"Created user: {phone}")

            # Create Primary Profile
            profile_res = await db.execute(select(models.Profile).where(models.Profile.owner_user_id == user.id, models.Profile.is_primary == True))
            profile = profile_res.scalars().first()
            if not profile:
                profile = models.Profile(
                    owner_user_id=user.id,
                    full_name="Test User",
                    relationship_type="self",
                    is_primary=True,
                    created_at=now,
                    updated_at=now
                )
                db.add(profile)
                print(f"Created primary profile for {phone}")
                
            await db.commit()
        print("Test user 1231231231 seeded successfully.")

    asyncio.run(run_multiple_seeds())

