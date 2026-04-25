from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Numeric,
    Date,
    Text,
    Boolean,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.schema import PrimaryKeyConstraint


Base = declarative_base()


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    organization_name = Column(String, nullable=False)
    address_line1 = Column(String)


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    middle_name = Column(String)
    date_of_birth = Column(Date, nullable=False)
    gender = Column(String)
    local_mrn_value = Column(String)
    contact_phone = Column(String)
    contact_email = Column(String)


class Practitioner(Base):
    __tablename__ = "practitioners"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String)
    middle_name = Column(String)
    prefix = Column(String)
    mci_reg_no = Column(String)
    local_identifier_system = Column(String)
    local_identifier_value = Column(String)


class PhrUser(Base):
    __tablename__ = "phr_users"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    middle_name = Column(String(100))
    gender = Column(String(10))
    date_of_birth = Column(Date)
    contact_phone = Column(String(255), index=True)
    contact_email = Column(String(255))
    address_line1 = Column(String(512))
    address_line2 = Column(String(512))
    city = Column(String(100))
    state = Column(String(100))
    postal_code = Column(String(20))
    country = Column(String(100))
    local_mrn_system = Column(String(255))
    local_mrn_value = Column(String(255))
    organization_id = Column(Integer)
    otp = Column(String(6))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("phr_users.id"), nullable=False, index=True)
    full_name = Column(String(150), nullable=False)
    relationship_type = Column("relationship", String(50), nullable=False, default="self")
    date_of_birth = Column(Date)
    gender = Column(String(20))
    blood_group = Column(String(10))
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    owner_user = relationship("PhrUser")
    caregivers = relationship("ProfileCaregiver", back_populates="profile", cascade="all, delete-orphan")


class ProfileCaregiver(Base):
    __tablename__ = "profile_caregivers"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    caregiver_user_id = Column(Integer, ForeignKey("phr_users.id"), nullable=False, index=True)
    can_view = Column(Boolean, default=True)
    can_edit = Column(Boolean, default=False)
    created_at = Column(DateTime)

    profile = relationship("Profile", back_populates="caregivers")
    caregiver_user = relationship("PhrUser")


class Encounter(Base):
    __tablename__ = "encounters"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    service_provider_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    patient = relationship("Patient")
    organization = relationship("Organization")


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    id = Column(Integer, primary_key=True, index=True)
    local_order_value = Column(String, index=True)
    order_date = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    requester_id = Column(Integer, ForeignKey("practitioners.id"))
    encounter_id = Column(Integer, ForeignKey("encounters.id"), nullable=False)

    patient = relationship("Patient")
    requester = relationship("Practitioner")
    encounter = relationship("Encounter")
    items = relationship("ServiceRequestItem", back_populates="service_request")
    observations = relationship("Observation", back_populates="service_request")


class Test(Base):
    __tablename__ = "tests"
    id = Column(Integer, primary_key=True, index=True)
    test_name = Column(String, nullable=False)
    method = Column(String)
    analytes = relationship("TestAnalyte", back_populates="test")


class ServiceRequestItem(Base):
    __tablename__ = "service_request_items"
    service_request_id = Column(Integer, ForeignKey("service_requests.id"), primary_key=True)
    test_id = Column(Integer, ForeignKey("tests.id"), primary_key=True)

    service_request = relationship("ServiceRequest", back_populates="items")
    test = relationship("Test")
    __table_args__ = (PrimaryKeyConstraint("service_request_id", "test_id"),)


class Unit(Base):
    __tablename__ = "units"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)


class TestAnalyte(Base):
    __tablename__ = "test_analytes"
    id = Column(Integer, primary_key=True, index=True)
    analyte_name = Column(String, nullable=False)
    test_id = Column(Integer, ForeignKey("tests.id"), nullable=False)
    test = relationship("Test", back_populates="analytes")


class ReferenceRange(Base):
    __tablename__ = "reference_ranges"
    id = Column(Integer, primary_key=True, index=True)
    text_range = Column(String)
    low_value = Column(Numeric)
    high_value = Column(Numeric)


class Observation(Base):
    __tablename__ = "observations"
    id = Column(Integer, primary_key=True, index=True)
    service_request_id = Column(Integer, ForeignKey("service_requests.id"), nullable=False)
    analyte_id = Column(Integer, ForeignKey("test_analytes.id"), nullable=False)
    value_numeric = Column(Numeric)
    value_string = Column(String)
    unit_id = Column(Integer, ForeignKey("units.id"))
    reference_range_id = Column(Integer, ForeignKey("reference_ranges.id"))
    interpretation_code = Column(String)

    service_request = relationship("ServiceRequest", back_populates="observations")
    test_analyte = relationship("TestAnalyte", foreign_keys=[analyte_id])
    unit = relationship("Unit")
    reference_range = relationship("ReferenceRange")


class UploadedRecord(Base):
    __tablename__ = "uploaded_records"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("phr_users.id"), nullable=False, index=True)
    record_type = Column(String(50), nullable=False, default="lab_report")
    title = Column(String(255), nullable=False)
    description = Column(Text)
    issued_date = Column(Date)
    source_facility = Column(String(255))
    source_doctor = Column(String(255))
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    mime_type = Column(String(120), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    upload_status = Column(String(40), nullable=False, default="uploaded")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    profile = relationship("Profile")
    owner_user = relationship("PhrUser")
    ocr_result = relationship("OCRExtraction", back_populates="record", uselist=False, cascade="all, delete-orphan")


class OCRExtraction(Base):
    __tablename__ = "ocr_extractions"
    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("uploaded_records.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    status = Column(String(40), nullable=False, default="pending")
    extracted_record_type = Column(String(50))
    extracted_title = Column(String(255))
    extracted_issued_date = Column(Date)
    extracted_source_facility = Column(String(255))
    extracted_source_doctor = Column(String(255))
    extracted_tags = Column(String(500))
    confidence = Column(Numeric)
    raw_text = Column(Text)
    is_confirmed = Column(Boolean, default=False)
    confirmed_tags = Column(String(500))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    record = relationship("UploadedRecord", back_populates="ocr_result")


class ShareLink(Base):
    __tablename__ = "share_links"
    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("uploaded_records.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("phr_users.id"), nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    recipient_email = Column(String(255))
    access_duration_hours = Column(Integer, default=24)
    created_at = Column(DateTime)
    expires_at = Column(DateTime, index=True)
    is_revoked = Column(Boolean, default=False, index=True)

    record = relationship("UploadedRecord")
    owner_user = relationship("PhrUser")
