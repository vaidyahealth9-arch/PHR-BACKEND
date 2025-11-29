from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from phr_backend.main import app, get_db, otp_store
from phr_backend import models
from datetime import datetime, date
import pytest
from httpx import AsyncClient, ASGITransport
import uuid

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with TestingSessionLocal() as db:
        yield db


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_read_root():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the PHR Backend Service"}


@pytest.mark.asyncio
async def test_auth_endpoints():
    # Create a user for testing
    async with TestingSessionLocal() as db:
        patient = models.Patient(
            first_name="Test",
            last_name="Patient",
            date_of_birth=date.fromisoformat("1990-01-01"),
            gender="Male",
            local_mrn_value="12345"
        )
        db.add(patient)
        await db.commit()
        await db.refresh(patient)
        user = models.PhrUser(id=uuid.uuid4(), phone="1234567890", patient_id=patient.id)
        db.add(user)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Test send-otp
        response = await ac.post("/api/v1/auth/send-otp", json={"phone_number": "1234567890"})
        assert response.status_code == 200
        assert response.json() == {"phone_number": "1234567890"}

        # Test verify-otp with incorrect OTP
        response = await ac.post(
            "/api/v1/auth/verify-otp", json={"phone_number": "1234567890", "otp": "000000"}
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid OTP"}

        # Test verify-otp with correct OTP
        response = await ac.post(
            "/api/v1/auth/verify-otp", json={"phone_number": "1234567890", "otp": otp_store["1234567890"]}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"
        token = response.json()["access_token"]

        # Test accessing protected endpoint without token
        response = await ac.get("/api/v1/records")
        assert response.status_code == 401

        # Test accessing protected endpoint with token
        response = await ac.get(
            "/api/v1/records", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_records_endpoints():
    # Create a user for testing
    async with TestingSessionLocal() as db:
        patient = models.Patient(
            first_name="Test",
            last_name="Patient",
            date_of_birth=date.fromisoformat("1990-01-01"),
            gender="Male",
            local_mrn_value="12345"
        )
        db.add(patient)
        await db.commit()
        await db.refresh(patient)
        user = models.PhrUser(id=uuid.uuid4(), phone="1234567890", patient_id=patient.id)
        db.add(user)
        await db.commit()
        organization = models.Organization(
            organization_name="Test Lab",
            address_line1="Test Address",
        )
        db.add(organization)
        await db.commit()
        await db.refresh(organization)
        practitioner = models.Practitioner(first_name="Test", last_name="Doctor", npi="1234567890")
        db.add(practitioner)
        await db.commit()
        await db.refresh(practitioner)
        encounter = models.Encounter(patient_id=patient.id, service_provider_id=organization.id)
        db.add(encounter)
        await db.commit()
        await db.refresh(encounter)
        service_request = models.ServiceRequest(
            local_order_value="123",
            order_date=datetime.fromisoformat("2023-01-01T00:00:00"),
            status="completed",
            patient_id=patient.id,
            requester_id=practitioner.id,
            encounter_id=encounter.id,
        )
        db.add(service_request)
        await db.commit()
        await db.refresh(service_request)
        test = models.Test(test_name="Test Test", method="Test Method")
        db.add(test)
        await db.commit()
        await db.refresh(test)
        service_request_item = models.ServiceRequestItem(
            service_request_id=service_request.id, test_id=test.id
        )
        db.add(service_request_item)
        test_analyte = models.TestAnalyte(analyte_name="Test Analyte", test_id=test.id)
        db.add(test_analyte)
        await db.commit()
        await db.refresh(test_analyte)
        unit = models.Unit(name="mg/dL")
        db.add(unit)
        await db.commit()
        await db.refresh(unit)
        reference_range = models.ReferenceRange(text_range="10-20", low_value=10, high_value=20)
        db.add(reference_range)
        await db.commit()
        await db.refresh(reference_range)
        observation = models.Observation(
            service_request_id=service_request.id,
            analyte_id=test_analyte.id,
            value_numeric=15,
            unit_id=unit.id,
            reference_range_id=reference_range.id,
        )
        db.add(observation)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Get a token
        await ac.post("/api/v1/auth/send-otp", json={"phone_number": "1234567890"})
        token = (
            (await ac.post(
                "/api/v1/auth/verify-otp",
                json={"phone_number": "1234567890", "otp": otp_store["1234567890"]},
            ))
        ).json()["access_token"]

        # Test get records
        response = await ac.get(
            "/api/v1/records", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

        # Test get record details
        record_id = response.json()[0]["order_id"]
        response = await ac.get(
            f"/api/v1/records/{record_id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert len(response.json()["analytes"]) == 1
        assert response.json()["analytes"][0]["method"] == "Test Method"

        # Test download report
        response = await ac.get(
            f"/api/v1/records/{record_id}/download",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
