import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.future import select
import models
import schemas


"""Test utilities for Part 6"""


@pytest.mark.asyncio
async def test_create_share_link(client: AsyncClient, db_session, authenticated_user):
    """Test creating a share link for a record"""
    # Upload a test record first
    record = models.UploadedRecord(
        profile_id=authenticated_user["profile_id"],
        owner_user_id=authenticated_user["user_id"],
        record_type="lab_report",
        title="Test Report",
        description="Test Description",
        issued_date=datetime.now().date(),
        source_facility="Test Lab",
        source_doctor="Dr. Test",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    # Create share link
    payload = {
        "recipient_email": "test@example.com",
        "access_duration_hours": 24,
    }
    
    response = await client.post(
        f"/api/v1/records/{record.id}/share",
        json=payload,
        headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "share_token" in data
    assert "link" in data
    assert "expires_at" in data
    assert data["recipient_email"] == "test@example.com"


@pytest.mark.asyncio
async def test_revoke_share_link(client: AsyncClient, db_session, authenticated_user):
    """Test revoking a share link"""
    # First create a share link
    record = models.UploadedRecord(
        profile_id=authenticated_user["profile_id"],
        owner_user_id=authenticated_user["user_id"],
        record_type="lab_report",
        title="Test Report",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    # Create share link
    payload = {"access_duration_hours": 24}
    response = await client.post(
        f"/api/v1/records/{record.id}/share",
        json=payload,
        headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
    )
    share_token = response.json()["share_token"]
    
    # Revoke the share link
    response = await client.delete(
        f"/api/v1/records/{record.id}/share/{share_token}",
        headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_share_links(client: AsyncClient, db_session, authenticated_user):
    """Test listing share links for a record"""
    record = models.UploadedRecord(
        profile_id=authenticated_user["profile_id"],
        owner_user_id=authenticated_user["user_id"],
        record_type="lab_report",
        title="Test Report",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    # Create multiple share links
    for i in range(2):
        payload = {"access_duration_hours": 24}
        await client.post(
            f"/api/v1/records/{record.id}/share",
            json=payload,
            headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
        )
    
    # List all share links
    response = await client.get(
        f"/api/v1/records/{record.id}/share",
        headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
    )
    
    assert response.status_code == 200
    links = response.json()
    assert len(links) >= 2


@pytest.mark.asyncio
async def test_summarize_report(client: AsyncClient, db_session, authenticated_user):
    """Test generating a report summary"""
    # Create record with OCR result
    record = models.UploadedRecord(
        profile_id=authenticated_user["profile_id"],
        owner_user_id=authenticated_user["user_id"],
        record_type="lab_report",
        title="Test Lab Report",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    ocr = models.OCRExtraction(
        record_id=record.id,
        status="completed",
        extracted_record_type="lab_report",
        extracted_title="Glucose Test",
        extracted_issued_date=datetime.now().date(),
        extracted_source_facility="Metro Lab",
        extracted_source_doctor="Dr. John",
        extracted_tags="glucose, fasting",
        confidence=0.95,
        is_confirmed=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ocr)
    await db_session.commit()
    
    # Get summary
    response = await client.post(
        f"/api/v1/records/{record.id}/summary",
        headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["record_id"] == record.id
    assert "summary_text" in data
    assert "key_findings" in data
    assert "clinical_significance" in data
    assert "disclaimer" in data


@pytest.mark.asyncio
async def test_get_analyte_trends(client: AsyncClient, db_session, authenticated_user):
    """Test getting trend data for an analyte"""
    # Create multiple records over time
    for i in range(3):
        record = models.UploadedRecord(
            profile_id=authenticated_user["profile_id"],
            owner_user_id=authenticated_user["user_id"],
            record_type="lab_report",
            title="Glucose Test",
            file_name=f"test{i}.pdf",
            file_path=f"/uploads/test{i}.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            upload_status="uploaded",
            created_at=datetime.now(timezone.utc) - timedelta(days=i),
            updated_at=datetime.now(timezone.utc) - timedelta(days=i),
        )
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)
        
        ocr = models.OCRExtraction(
            record_id=record.id,
            status="completed",
            extracted_tags="glucose",
            is_confirmed=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=i),
            updated_at=datetime.now(timezone.utc) - timedelta(days=i),
        )
        db_session.add(ocr)
        await db_session.commit()
    
    # Get the first record to get trend data for
    result = await db_session.execute(
        select(models.UploadedRecord)
        .filter(models.UploadedRecord.profile_id == authenticated_user["profile_id"])
        .limit(1)
    )
    first_record = result.scalars().first()
    
    response = await client.get(
        f"/api/v1/records/{first_record.id}/trends/glucose?days=30",
        headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["analyte"] == "glucose"
    assert "trend_data" in data
    assert "statistics" in data


@pytest.mark.asyncio
async def test_download_report_html(client: AsyncClient, db_session, authenticated_user):
    """Test downloading report as HTML"""
    record = models.UploadedRecord(
        profile_id=authenticated_user["profile_id"],
        owner_user_id=authenticated_user["user_id"],
        record_type="lab_report",
        title="Test Report",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    ocr = models.OCRExtraction(
        record_id=record.id,
        status="completed",
        extracted_record_type="lab_report",
        extracted_title="Test",
        is_confirmed=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ocr)
    await db_session.commit()
    
    response = await client.get(
        f"/api/v1/records/{record.id}/download?format=html",
        headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
    )
    
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_access_shared_report_via_public_link(client: AsyncClient, db_session, authenticated_user):
    """Test accessing a shared report without authentication"""
    # Create and share a record
    record = models.UploadedRecord(
        profile_id=authenticated_user["profile_id"],
        owner_user_id=authenticated_user["user_id"],
        record_type="lab_report",
        title="Shared Report",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    ocr = models.OCRExtraction(
        record_id=record.id,
        status="completed",
        is_confirmed=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ocr)
    await db_session.commit()
    
    # Create share link
    response = await client.post(
        f"/api/v1/records/{record.id}/share",
        json={"access_duration_hours": 24},
        headers={"Authorization": f"Bearer {authenticated_user['access_token']}"},
    )
    share_token = response.json()["share_token"]
    
    # Access via public link (no auth)
    response = await client.get(f"/api/v1/share/{share_token}")
    
    assert response.status_code == 200
    data = response.json()
    assert "record" in data
    assert "summary" in data
    assert data["record"]["id"] == record.id


@pytest.mark.asyncio
async def test_share_link_access_denied_after_expiry(client: AsyncClient, db_session, authenticated_user):
    """Test that expired share links are denied"""
    # Create a record and share with 0 hours duration (immediately expired)
    record = models.UploadedRecord(
        profile_id=authenticated_user["profile_id"],
        owner_user_id=authenticated_user["user_id"],
        record_type="lab_report",
        title="Test Report",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    # Manually create an expired share link
    import secrets
    share_link = models.ShareLink(
        record_id=record.id,
        owner_user_id=authenticated_user["user_id"],
        token=secrets.token_urlsafe(32),
        recipient_email=None,
        access_duration_hours=0,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        is_revoked=False,
    )
    db_session.add(share_link)
    await db_session.commit()
    
    # Try to access expired link
    response = await client.get(f"/api/v1/share/{share_link.token}")
    
    assert response.status_code == 404
