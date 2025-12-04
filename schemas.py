from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import Optional
import uuid

class PhrUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    phone: str
    patient_id: int

class Patient(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    local_mrn_value: str


class Practitioner(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: str
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    prefix: Optional[str] = None


class Organization(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_name: str
    address_line1: str
    logo_url: Optional[str] = None


class Encounter(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    service_provider_id: int
    organization: Organization


class SendOTPRequest(BaseModel):
    phone_number: str


class VerifyOTPRequest(BaseModel):
    phone_number: str
    otp: str


class Token(BaseModel):
    access_token: str
    token_type: str


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    order_id: int
    display_id: str
    date: str
    lab_name: str
    status: str
    test_names: list[str]
    patient: Optional[Patient] = None
    encounter: Optional[Encounter] = None
    requester: Optional[Practitioner] = None


class Analyte(BaseModel):
    name: str
    result: str
    unit: str
    reference_range: str
    status_color: str
    method: str


class RecordDetails(BaseModel):
    order_details: Record
    analytes: list[Analyte]


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    abha_address: Optional[str] = None
    abha_id: Optional[str] = None
    # Computed fields
    full_name: Optional[str] = None
    age: Optional[int] = None
