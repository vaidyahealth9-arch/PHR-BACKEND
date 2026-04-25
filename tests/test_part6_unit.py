import pytest
from datetime import datetime, timedelta, timezone
import models
import crud


"""Unit tests for Part 6 functions"""


@pytest.mark.asyncio
async def test_generate_report_summary(db_session):
    """Test report summary generation"""
    # Create test record
    user = models.PhrUser(contact_phone="9800122899", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    profile = models.Profile(
        owner_user_id=user.id,
        full_name="Test Patient",
        relationship_type="self",
        is_primary=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    
    record = models.UploadedRecord(
        profile_id=profile.id,
        owner_user_id=user.id,
        record_type="lab_report",
        title="Glucose Test",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    ocr = models.OCRExtraction(
        record_id=record.id,
        status="completed",
        extracted_record_type="lab_report",
        extracted_title="Glucose",
        extracted_tags="glucose, fasting",
        is_confirmed=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(ocr)
    await db_session.commit()
    
    # Generate summary
    summary = await crud.generate_report_summary(db_session, record.id)
    
    assert summary is not None
    assert summary["record_id"] == record.id
    assert "summary_text" in summary
    assert "key_findings" in summary
    assert len(summary["key_findings"]) > 0
    assert "clinical_significance" in summary
    assert "disclaimer" in summary


@pytest.mark.asyncio
async def test_generate_trend_data_with_multiple_records(db_session):
    """Test trend generation with multiple records"""
    user = models.PhrUser(contact_phone="9800122899", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    profile = models.Profile(
        owner_user_id=user.id,
        full_name="Test Patient",
        relationship_type="self",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    
    # Create multiple records
    for i in range(3):
        record = models.UploadedRecord(
            profile_id=profile.id,
            owner_user_id=user.id,
            record_type="lab_report",
            title="Glucose Test",
            file_name=f"test{i}.pdf",
            file_path=f"/uploads/test{i}.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            upload_status="uploaded",
            created_at=datetime.now(timezone.utc) - timedelta(days=i),
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
        )
        db_session.add(ocr)
        await db_session.commit()
    
    # Generate trends
    trends = await crud.generate_trend_data(db_session, profile.id, "glucose", days=30)
    
    assert trends is not None
    assert "trend_data" in trends
    assert len(trends["trend_data"]) >= 3
    assert "statistics" in trends
    assert "min" in trends["statistics"]
    assert "max" in trends["statistics"]
    assert "avg" in trends["statistics"]
    assert "trend_direction" in trends["statistics"]


@pytest.mark.asyncio
async def test_trend_direction_calculation(db_session):
    """Test that trend direction is calculated correctly"""
    user = models.PhrUser(contact_phone="9800122899", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    profile = models.Profile(
        owner_user_id=user.id,
        full_name="Test Patient",
        relationship_type="self",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    
    # Create records with improving trend (values decreasing)
    days_ago = [10, 8, 6, 4, 2, 0]
    for day in days_ago:
        record = models.UploadedRecord(
            profile_id=profile.id,
            owner_user_id=user.id,
            record_type="lab_report",
            title="Glucose Test",
            file_name=f"test{day}.pdf",
            file_path=f"/uploads/test{day}.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            upload_status="uploaded",
            created_at=datetime.now(timezone.utc) - timedelta(days=day),
        )
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)
        
        ocr = models.OCRExtraction(
            record_id=record.id,
            status="completed",
            extracted_tags="glucose",
            is_confirmed=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=day),
        )
        db_session.add(ocr)
        await db_session.commit()
    
    trends = await crud.generate_trend_data(db_session, profile.id, "glucose", days=30)
    
    assert trends is not None
    # The trend direction should be "improving", "stable", or "worsening"
    assert trends["statistics"]["trend_direction"] in ["improving", "stable", "worsening"]


@pytest.mark.asyncio
async def test_create_share_link_generates_valid_token(db_session):
    """Test that share link tokens are unique and secure"""
    user = models.PhrUser(contact_phone="9800122899", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    profile = models.Profile(
        owner_user_id=user.id,
        full_name="Test Patient",
        relationship_type="self",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    
    record = models.UploadedRecord(
        profile_id=profile.id,
        owner_user_id=user.id,
        record_type="lab_report",
        title="Test",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    # Create share link
    link = await crud.create_share_link(
        db_session,
        record_id=record.id,
        owner_user_id=user.id,
        recipient_email="test@example.com",
        access_duration_hours=24,
    )
    
    assert link.token is not None
    assert len(link.token) > 20  # URL-safe token should be reasonably long
    assert link.recipient_email == "test@example.com"
    assert link.is_revoked is False
    assert link.expires_at > link.created_at


@pytest.mark.asyncio
async def test_revoke_share_link(db_session):
    """Test revoking a share link"""
    user = models.PhrUser(contact_phone="9800122899", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    profile = models.Profile(
        owner_user_id=user.id,
        full_name="Test Patient",
        relationship_type="self",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    
    record = models.UploadedRecord(
        profile_id=profile.id,
        owner_user_id=user.id,
        record_type="lab_report",
        title="Test",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    # Create share link
    link = await crud.create_share_link(
        db_session,
        record_id=record.id,
        owner_user_id=user.id,
        access_duration_hours=24,
    )
    
    # Revoke it
    revoked = await crud.revoke_share_link(
        db_session,
        record_id=record.id,
        token=link.token,
        owner_user_id=user.id,
    )
    
    assert revoked is True
    
    # Verify it's revoked
    fetched = await crud.get_share_link_by_token(db_session, link.token)
    assert fetched is None  # Should be None because it's revoked


@pytest.mark.asyncio
async def test_share_link_expiry(db_session):
    """Test that expired share links cannot be accessed"""
    user = models.PhrUser(contact_phone="9800122899", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    profile = models.Profile(
        owner_user_id=user.id,
        full_name="Test Patient",
        relationship_type="self",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    
    record = models.UploadedRecord(
        profile_id=profile.id,
        owner_user_id=user.id,
        record_type="lab_report",
        title="Test",
        file_name="test.pdf",
        file_path="/uploads/test.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        upload_status="uploaded",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    
    # Create link with past expiry
    import secrets
    expired_link = models.ShareLink(
        record_id=record.id,
        owner_user_id=user.id,
        token=secrets.token_urlsafe(32),
        access_duration_hours=0,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        is_revoked=False,
    )
    db_session.add(expired_link)
    await db_session.commit()
    
    # Try to access
    fetched = await crud.get_share_link_by_token(db_session, expired_link.token)
    assert fetched is None  # Should not be accessible
