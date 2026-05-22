from datetime import date
from typing import Literal, Optional, Dict, Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiErrorResponse(BaseModel):
    """
    Standard API error response for all PHR endpoints.
    
    Ensures consistent error handling across the service.
    All exceptions are mapped to this schema for client consumption.
    """
    timestamp: str
    status: int
    error: str
    message: str
    path: str
    trace_id: str
    details: Optional[Dict[str, Any]] = None
    
    @staticmethod
    def create(
        status: int,
        error: str,
        message: str,
        path: str,
        trace_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> "ApiErrorResponse":
        """Create error response with auto-generated trace ID if needed"""
        from datetime import datetime
        if trace_id is None:
            trace_id = str(uuid.uuid4())
        
        return ApiErrorResponse(
            timestamp=datetime.utcnow().isoformat(),
            status=status,
            error=error,
            message=message,
            path=path,
            trace_id=trace_id,
            details=details
        )


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
    refresh_token: str
    token_type: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class RecordMetadata(BaseModel):
    record_type: str
    source: str
    source_type: Literal["lab"] = "lab"
    tags: list[str] = Field(default_factory=list)


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    order_id: int
    display_id: str
    date: str
    lab_name: str
    status: str
    test_names: list[str]
    metadata: RecordMetadata
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


class RecordListResponse(BaseModel):
    items: list[Record]
    total: int
    page: int
    page_size: int
    total_pages: int


class UploadRecordResponse(BaseModel):
    record_id: int
    profile_id: int
    upload_status: str
    file_name: str
    file_size_bytes: int
    ocr_status: str


class OCRExtractionResponse(BaseModel):
    record_id: int
    status: str
    extracted_record_type: Optional[str] = None
    extracted_title: Optional[str] = None
    extracted_issued_date: Optional[date] = None
    extracted_source_facility: Optional[str] = None
    extracted_source_doctor: Optional[str] = None
    extracted_tags: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    is_confirmed: bool = False
    confirmed_tags: list[str] = Field(default_factory=list)


class OCRConfirmRequest(BaseModel):
    title: Optional[str] = None
    record_type: Optional[str] = None
    issued_date: Optional[date] = None
    source_facility: Optional[str] = None
    source_doctor: Optional[str] = None
    confirmed_tags: list[str] = Field(default_factory=list)


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    contact_phone: str
    contact_email: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

    @field_validator(
        "first_name",
        "last_name",
        "contact_phone",
        "contact_email",
        "gender",
        "address_line1",
        "city",
        "state",
        "postal_code",
        "country",
    )
    @classmethod
    def normalize_text(cls, value: Optional[str]):
        if value is None:
            return value
        cleaned = value.strip()
        return cleaned or None


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
    full_name: Optional[str] = None
    age: Optional[int] = None


class UserProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    contact_email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

    @field_validator(
        "first_name",
        "last_name",
        "middle_name",
        "gender",
        "contact_email",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
    )
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]):
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None


class ProfileSummary(BaseModel):
    id: str
    full_name: str
    relationship: str
    is_primary: bool = False
    owner_user_id: Optional[int] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None


ALLOWED_RELATIONSHIPS = {"self", "spouse", "child", "parent", "sibling", "other", "caregiver"}


class ProfileCreateRequest(BaseModel):
    full_name: str
    relationship: str = "other"
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str):
        if not value or len(value.strip()) < 2:
            raise ValueError("full_name must have at least 2 characters")
        return value.strip()

    @field_validator("relationship")
    @classmethod
    def validate_relationship(cls, value: str):
        normalized = value.strip().lower()
        if normalized not in ALLOWED_RELATIONSHIPS:
            raise ValueError("relationship is invalid")
        return normalized


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    relationship: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: Optional[str]):
        if value is None:
            return value
        if len(value.strip()) < 2:
            raise ValueError("full_name must have at least 2 characters")
        return value.strip()

    @field_validator("relationship")
    @classmethod
    def validate_relationship(cls, value: Optional[str]):
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in ALLOWED_RELATIONSHIPS:
            raise ValueError("relationship is invalid")
        return normalized


class CaregiverGrantRequest(BaseModel):
    caregiver_user_phone: str
    can_view: bool = True
    can_edit: bool = False


class CaregiverPermissionResponse(BaseModel):
    id: int
    profile_id: int
    caregiver_user_id: int
    caregiver_user_phone: Optional[str] = None
    can_view: bool
    can_edit: bool


class ApiErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: Optional[dict | list | str] = None


class ApiErrorEnvelope(BaseModel):
    error: ApiErrorBody


class TrendDataPoint(BaseModel):
    date: date
    value: float
    unit: str
    status: Literal["normal", "low", "high", "critical"] = "normal"


class TrendStatistics(BaseModel):
    min: float
    max: float
    avg: float
    trend_direction: Literal["improving", "stable", "worsening"]


class ReferenceRange(BaseModel):
    low: Optional[float] = None
    high: Optional[float] = None
    unit: str


class TrendComparisonResponse(BaseModel):
    profile_id: int
    analyte: str
    trend_data: list[TrendDataPoint]
    statistics: TrendStatistics
    reference_range: Optional[ReferenceRange] = None


class KeyFinding(BaseModel):
    analyte: str
    value: float
    unit: str
    status: Literal["normal", "low", "high", "critical"]
    clinical_note: str


class ReportSummaryResponse(BaseModel):
    record_id: int
    title: str
    summary_text: str
    key_findings: list[KeyFinding]
    clinical_significance: str
    generated_at: str
    confidence: float
    disclaimer: str


class ShareLinkCreateRequest(BaseModel):
    recipient_email: Optional[str] = None
    access_duration_hours: int = 24

    @field_validator("access_duration_hours")
    @classmethod
    def validate_duration(cls, value: int):
        if value < 1 or value > 8760:
            raise ValueError("access_duration_hours must be between 1 and 8760")
        return value


class ShareLinkResponse(BaseModel):
    share_token: str
    link: str
    expires_at: str
    recipient_email: Optional[str] = None


class ShareLinkSummary(BaseModel):
    id: int
    token: str
    recipient_email: Optional[str] = None
    expires_at: str
    is_revoked: bool
    created_at: str
