from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Numeric,
    Date,
    Text,
    UUID as UUID_GENERIC,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.schema import PrimaryKeyConstraint
import uuid


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
    last_name = Column(String, nullable=False)
    npi = Column(String, unique=True)


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
    abha_address = Column(String(255))
    abha_id = Column(String(255))
    abha_id_system = Column(String(255))
    abdm_link_status = Column(String(50))
    abdm_status_message = Column(Text)
    abdm_last_linked_at = Column(DateTime)
    local_mrn_system = Column(String(255))
    local_mrn_value = Column(String(255))
    organization_id = Column(Integer)
    otp = Column(String(6))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


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


class DiagnosticReport(Base):
    __tablename__ = "diagnostic_reports"
    id = Column(Integer, primary_key=True, index=True)
    service_request_id = Column(Integer, ForeignKey("service_requests.id"), nullable=False)
    report_text = Column(Text)
    service_request = relationship("ServiceRequest")
