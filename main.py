from datetime import date, datetime, timezone
import logging
import os
import random
import re
import string
import time
import uuid
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, HTTPAuthorizationCredentials, HTTPBearer
from fastapi.templating import Jinja2Templates

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError
from sqlalchemy import and_, func
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.future import select
from starlette.exceptions import HTTPException as StarletteHTTPException

import auth
import crud
import models
import schemas
from integrations import lims_client
from ocr_service import infer_issued_date, infer_record_type, infer_tags
from auth_lifecycle import AuthLifecycleManager, OTPPolicy
from database import SessionLocal, engine
from record_storage import build_record_storage
from whatsapp_service import send_otp_via_whatsapp, is_whatsapp_configured

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _normalize_mobile(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    return digits[-10:] if len(digits) >= 10 else digits


def _is_internal_cloud_auth_enabled() -> bool:
    auth_mode = os.getenv("INTERNAL_AUTH_MODE", "auto").strip().lower()
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    if auth_mode == "oidc":
        return True
    if auth_mode == "local":
        return False
    return environment in {"prod", "production"}


def _get_allowed_internal_service_accounts() -> set[str]:
    raw = os.getenv("INTERNAL_ALLOWED_SERVICE_ACCOUNTS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def _authorize_internal_request(request: Request, target_mobile: str | None = None) -> None:
    # Compliance guard: caller must declare the user mobile and it must match the requested patient mobile.
    expected_mobile = _normalize_mobile(target_mobile)
    caller_mobile = _normalize_mobile(request.headers.get("X-User-Mobile"))
    if expected_mobile and caller_mobile != expected_mobile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INTERNAL_PATIENT_SCOPE_VIOLATION",
                "message": "Caller is not authorized for the requested patient scope",
            },
        )

    if _is_internal_cloud_auth_enabled():
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INTERNAL_AUTH_MISSING", "message": "Missing bearer token"},
            )

        token = auth_header.split(" ", 1)[1].strip()
        audience = (
            os.getenv("PHR_SERVICE_URL_CLOUD")
            or os.getenv("PHR_SERVICE_URL")
            or str(request.base_url).rstrip("/")
        )
        try:
            payload = google_id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                audience=audience,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INTERNAL_AUTH_INVALID", "message": f"Invalid service token: {exc}"},
            )

        caller_email = str(payload.get("email") or "").strip().lower()
        allowed_accounts = _get_allowed_internal_service_accounts()
        if allowed_accounts and caller_email not in allowed_accounts:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INTERNAL_CALLER_NOT_ALLOWED",
                    "message": "Calling service account is not authorized",
                },
            )
        return

    expected_secret = os.getenv("INTERNAL_SECRET_KEY", "").strip()
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_AUTH_NOT_CONFIGURED",
                "message": "INTERNAL_SECRET_KEY is not configured",
            },
        )

    provided_secret = request.headers.get("X-Internal-Secret", "").strip()
    if provided_secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INTERNAL_AUTH_INVALID", "message": "Invalid internal secret"},
        )


def _get_cors_origins() -> list[str]:
    raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if raw_origins:
        return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]


record_storage = build_record_storage()

app = FastAPI(title="PHR Backend API", version="1.0")
APP_STARTED_AT = datetime.now(timezone.utc)

# CORS Configuration - Allow frontend to make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



auth_lifecycle = AuthLifecycleManager(
    policy=OTPPolicy(
        otp_ttl_seconds=int(os.getenv("OTP_TTL_SECONDS", "300")),
        resend_cooldown_seconds=int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "30")),
        max_sends_per_hour=int(os.getenv("OTP_MAX_SENDS_PER_HOUR", "5")),
        max_verify_attempts=int(os.getenv("OTP_MAX_VERIFY_ATTEMPTS", "5")),
        verification_lock_minutes=int(os.getenv("OTP_VERIFICATION_LOCK_MINUTES", "15")),
    )
)


def _error_payload(
    request: Request,
    code: str,
    message: str,
    details: dict | list | str | None = None,
):
    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", "unknown"),
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


@app.middleware("http")
async def request_id_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    logger.info(
        "request_start request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "request_end request_id=%s method=%s path=%s status=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        code = str(exc.detail.get("code", f"HTTP_{exc.status_code}"))
        message = str(exc.detail.get("message", "Request failed"))
        details = exc.detail.get("details")
    else:
        code = f"HTTP_{exc.status_code}"
        message = str(exc.detail)
        details = None

    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(request, code=code, message=message, details=details),
        headers=exc.headers,
    )


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code", f"HTTP_{exc.status_code}"))
        message = str(detail.get("message", "Request failed"))
        details = detail.get("details")
    else:
        code = f"HTTP_{exc.status_code}"
        message = str(detail)
        details = None

    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(request, code=code, message=message, details=details),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_error_payload(
            request,
            code="VALIDATION_ERROR",
            message="Invalid request payload",
            details=exc.errors(),
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_payload(
            request,
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred",
        ),
    )


# Dependency
async def get_db():
    async with SessionLocal() as db:
        yield db


@app.get("/")
def read_root():
    return {"message": "Welcome to the PHR Backend Service"}


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "phr-backend",
        "version": app.version,
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


@app.get("/live")
async def liveness() -> dict:
    uptime_seconds = int((datetime.now(timezone.utc) - APP_STARTED_AT).total_seconds())
    return {
        "status": "alive",
        "uptime_seconds": max(0, uptime_seconds),
    }


@app.get("/ready")
async def readiness(db: Session = Depends(get_db)) -> dict:
    started = time.perf_counter()
    await db.execute(select(1))
    latency_ms = int((time.perf_counter() - started) * 1000)

    return {
        "status": "ready",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": {
            "api": {"status": "ok"},
            "database": {
                "status": "ok",
                "latency_ms": max(0, latency_ms),
            },
        },
    }


@app.post("/api/v1/auth/signup", response_model=schemas.UserProfile)
async def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = await crud.get_user_by_phone(db, phone_number=user.contact_phone)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail={"code": "USER_ALREADY_EXISTS", "message": "User with this phone number already exists"},
        )
    return await crud.create_user(db=db, user=user)


@app.post("/api/v1/auth/send-otp", response_model=schemas.SendOTPRequest)
async def send_otp(request: schemas.SendOTPRequest, db: Session = Depends(get_db)):
    db_user = await crud.get_user_by_phone(db, phone_number=request.phone_number)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail={"code": "USER_NOT_FOUND", "message": "User not found"},
        )

    allowed, error = auth_lifecycle.can_send_otp(request.phone_number)
    if not allowed:
        raise HTTPException(status_code=429, detail=error)
    
    # Generate random 6-digit OTP
    # For development: use fixed OTP 123456 for test users
    if (request.phone_number in ["9800122899", "1231231231"]) and os.getenv("ENVIRONMENT", "development") == "development":
        otp = "123456"  # Fixed OTP for test users in development
        logger.info(f"Using fixed OTP for test user: {request.phone_number}")

    else:
        otp = "".join(random.choices(string.digits, k=6))


    auth_lifecycle.issue_otp(request.phone_number, otp)
    
    # Store OTP in database
    db_user.otp = otp
    await db.commit()
    
    # Send OTP via WhatsApp
    whatsapp_result = await send_otp_via_whatsapp(request.phone_number, otp)
    
    if whatsapp_result["success"]:
        logger.info(f"OTP sent via WhatsApp to {request.phone_number}")
    else:
        # Log OTP to console if WhatsApp fails (for development/debugging)
        logger.warning(f"WhatsApp send failed: {whatsapp_result['message']}")
        logger.info(f"OTP for {request.phone_number}: {otp} (logged for development)")
    
    return {"phone_number": request.phone_number}


@app.post("/api/v1/auth/verify-otp", response_model=schemas.Token)
async def verify_otp(request: schemas.VerifyOTPRequest, db: Session = Depends(get_db)):
    db_user = await crud.get_user_by_phone(db, phone_number=request.phone_number)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail={"code": "USER_NOT_FOUND", "message": "User not found"},
        )

    otp_verified, otp_error = auth_lifecycle.verify_otp(request.phone_number, request.otp)
    if not otp_verified:
        status_code = 429 if otp_error and otp_error.get("code") == "OTP_VERIFICATION_LOCKED" else 400
        raise HTTPException(status_code=status_code, detail=otp_error)

    # Clear the OTP after successful verification
    db_user.otp = None
    await db.commit()

    # Build user's full name
    full_name = db_user.first_name or ""
    if db_user.last_name:
        full_name = f"{full_name} {db_user.last_name}".strip()
    if not full_name:
        full_name = "User"

    access_token = auth.create_access_token(
        data={
            "sub": db_user.contact_phone,
            "user_id": str(db_user.id),
            "name": full_name,
        }
    )
    refresh_token = auth.create_refresh_token(
        data={
            "sub": db_user.contact_phone,
            "user_id": str(db_user.id),
            "name": full_name,
        }
    )
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
optional_bearer = HTTPBearer(auto_error=False)


@app.post("/api/v1/auth/refresh")
async def refresh_token(request: schemas.RefreshTokenRequest, db: Session = Depends(get_db)):
    try:
        payload = auth.decode_token(request.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_REFRESH_TOKEN", "message": "Invalid refresh token"},
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN_TYPE", "message": "Expected refresh token"},
        )

    jti = payload.get("jti")
    if auth_lifecycle.is_token_revoked(jti):
        raise HTTPException(
            status_code=401,
            detail={"code": "TOKEN_REVOKED", "message": "Refresh token has been revoked"},
        )

    phone_number: str | None = payload.get("sub")
    if not phone_number:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_REFRESH_TOKEN", "message": "Invalid token subject"},
        )

    db_user = await crud.get_user_by_phone(db, phone_number=phone_number)
    if not db_user:
        raise HTTPException(
            status_code=401,
            detail={"code": "USER_NOT_FOUND", "message": "User not found for refresh token"},
        )

    full_name = db_user.first_name or ""
    if db_user.last_name:
        full_name = f"{full_name} {db_user.last_name}".strip()
    if not full_name:
        full_name = "User"

    # Rotate refresh token
    auth_lifecycle.revoke_token_jti(jti)

    new_access_token = auth.create_access_token(
        data={"sub": db_user.contact_phone, "user_id": str(db_user.id), "name": full_name}
    )
    new_refresh_token = auth.create_refresh_token(
        data={"sub": db_user.contact_phone, "user_id": str(db_user.id), "name": full_name}
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@app.post("/api/v1/auth/logout")
async def logout(
    request: schemas.LogoutRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
):
    # Revoke access token (if provided)
    if credentials and credentials.credentials:
        try:
            access_payload = auth.decode_token(credentials.credentials)
            auth_lifecycle.revoke_token_jti(access_payload.get("jti"))
        except JWTError:
            pass

    # Revoke refresh token (if provided)
    if request.refresh_token:
        try:
            refresh_payload = auth.decode_token(request.refresh_token)
            auth_lifecycle.revoke_token_jti(refresh_payload.get("jti"))
        except JWTError:
            pass

    return {"message": "Logged out"}


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=401,
        detail={"code": "UNAUTHORIZED", "message": "Could not validate credentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = auth.decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception

        if auth_lifecycle.is_token_revoked(payload.get("jti")):
            raise HTTPException(
                status_code=401,
                detail={"code": "TOKEN_REVOKED", "message": "Access token has been revoked"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        phone_number: str = payload.get("sub")
        if phone_number is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = await crud.get_user_by_phone(db, phone_number=phone_number)
    if user is None:
        raise credentials_exception
    return user


def _to_user_profile_response(user: models.PhrUser) -> schemas.UserProfile:
    full_name = user.first_name or ""
    if user.middle_name:
        full_name = f"{full_name} {user.middle_name}".strip()
    if user.last_name:
        full_name = f"{full_name} {user.last_name}".strip()
    if not full_name:
        full_name = "User"

    age = None
    if user.date_of_birth:
        today = datetime.now().date()
        age = today.year - user.date_of_birth.year
        if (today.month, today.day) < (user.date_of_birth.month, user.date_of_birth.day):
            age -= 1

    return schemas.UserProfile(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        middle_name=user.middle_name,
        gender=user.gender,
        date_of_birth=user.date_of_birth,
        contact_phone=user.contact_phone,
        contact_email=user.contact_email,
        address_line1=user.address_line1,
        address_line2=user.address_line2,
        city=user.city,
        state=user.state,
        postal_code=user.postal_code,
        country=user.country,
        full_name=full_name,
        age=age,
    )


@app.get("/api/v1/auth/me", response_model=schemas.UserProfile)
async def get_current_user_profile(
    current_user: models.PhrUser = Depends(get_current_user),
):
    """Get the current logged-in user's profile"""
    return _to_user_profile_response(current_user)


@app.put("/api/v1/auth/me", response_model=schemas.UserProfile)
async def update_current_user_profile(
    payload: schemas.UserProfileUpdateRequest,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updated_user = await crud.update_user_profile(db, current_user, payload)
    return _to_user_profile_response(updated_user)

@app.get("/api/v1/auth/users/by-phone/{phone_number}", response_model=schemas.UserProfile)
async def get_user_by_phone_number(
    request: Request,
    phone_number: str,
    db: Session = Depends(get_db),
):
    """Integration endpoint for LIMS to fetch PHR user details by mobile number."""
    _authorize_internal_request(request, target_mobile=phone_number)

    db_user = await crud.get_user_by_phone(db, phone_number=phone_number)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail={"code": "USER_NOT_FOUND", "message": "User not found with this phone number"},
        )
    
    # Calculate full name
    full_name = db_user.first_name or ""
    if db_user.middle_name:
        full_name = f"{full_name} {db_user.middle_name}".strip()
    if db_user.last_name:
        full_name = f"{full_name} {db_user.last_name}".strip()
    if not full_name:
        full_name = "User"
    
    # Calculate age
    age = None
    if db_user.date_of_birth:
        today = datetime.now().date()
        age = today.year - db_user.date_of_birth.year
        if (today.month, today.day) < (db_user.date_of_birth.month, db_user.date_of_birth.day):
            age -= 1
            
    return schemas.UserProfile(
        id=db_user.id,
        first_name=db_user.first_name,
        last_name=db_user.last_name,
        middle_name=db_user.middle_name,
        gender=db_user.gender,
        date_of_birth=db_user.date_of_birth,
        contact_phone=db_user.contact_phone,
        contact_email=db_user.contact_email,
        address_line1=db_user.address_line1,
        address_line2=db_user.address_line2,
        city=db_user.city,
        state=db_user.state,
        postal_code=db_user.postal_code,
        country=db_user.country,
        full_name=full_name,
        age=age,
    )

@app.get("/api/v1/linked/lims/reports")
async def get_linked_lims_reports(current_user: models.PhrUser = Depends(get_current_user)):
    """Fetch LIMS reports for the current PHR user based on mobile number matching"""
    logger.info(f"API CALL: get_linked_lims_reports for {current_user.contact_phone}")
    return await lims_client.get_lims_reports(current_user.contact_phone)


@app.get("/api/v1/linked/lims/reports/{report_id}/pdf")
async def download_linked_lims_report_pdf(
    report_id: int,
    report_type: str = Query(default="regular", alias="report_type"),
    with_header: bool = Query(default=True, alias="with_header"),
    current_user: models.PhrUser = Depends(get_current_user),
):
    """Proxy the signed LIMS report PDF to the authenticated PHR user."""
    logger.info(f"API CALL: download_linked_lims_report_pdf for report_id={report_id}, user={current_user.contact_phone}")
    pdf_result = await lims_client.get_lims_report_pdf(
        report_id,
        current_user.contact_phone,
        report_type=report_type,
        with_header=with_header,
    )
    if not pdf_result:
        raise HTTPException(
            status_code=404,
            detail={"code": "REPORT_PDF_NOT_FOUND", "message": "Signed report PDF not available"},
        )

    pdf_bytes, content_type = pdf_result
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type=content_type or "application/pdf",
        headers={"Content-Disposition": f"inline; filename=report-{report_id}.pdf"},
    )

@app.get("/api/v1/linked/lims/bills")
async def get_linked_lims_bills(current_user: models.PhrUser = Depends(get_current_user)):
    """Fetch LIMS bills for the current PHR user based on mobile number matching"""
    logger.info(f"API CALL: get_linked_lims_bills for {current_user.contact_phone}")
    return await lims_client.get_lims_bills(current_user.contact_phone)


@app.get("/api/v1/linked/lims/analyte-history")
async def get_linked_lims_analyte_history(current_user: models.PhrUser = Depends(get_current_user)):
    """Fetch LIMS analyte history for the current PHR user based on mobile number matching"""
    logger.info(f"API CALL: get_linked_lims_analyte_history for {current_user.contact_phone}")
    return await lims_client.get_lims_analyte_history(current_user.contact_phone)


def _to_profile_summary(profile: models.Profile) -> schemas.ProfileSummary:
    return schemas.ProfileSummary(
        id=str(profile.id),
        full_name=profile.full_name,
        relationship=profile.relationship_type,
        is_primary=bool(profile.is_primary),
        owner_user_id=profile.owner_user_id,
        date_of_birth=profile.date_of_birth,
        gender=profile.gender,
        blood_group=profile.blood_group,
    )


def _to_caregiver_permission_response(permission: models.ProfileCaregiver) -> schemas.CaregiverPermissionResponse:
    return schemas.CaregiverPermissionResponse(
        id=permission.id,
        profile_id=permission.profile_id,
        caregiver_user_id=permission.caregiver_user_id,
        caregiver_user_phone=permission.caregiver_user.contact_phone if permission.caregiver_user else None,
        can_view=bool(permission.can_view),
        can_edit=bool(permission.can_edit),
    )


def _split_csv_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _to_ocr_response(record: models.UploadedRecord) -> schemas.OCRExtractionResponse:
    ocr = record.ocr_result
    return schemas.OCRExtractionResponse(
        record_id=record.id,
        status=ocr.status if ocr else "pending",
        extracted_record_type=ocr.extracted_record_type if ocr else None,
        extracted_title=ocr.extracted_title if ocr else None,
        extracted_issued_date=ocr.extracted_issued_date if ocr else None,
        extracted_source_facility=ocr.extracted_source_facility if ocr else None,
        extracted_source_doctor=ocr.extracted_source_doctor if ocr else None,
        extracted_tags=_split_csv_tags(ocr.extracted_tags if ocr else None),
        confidence=float(ocr.confidence) if ocr and ocr.confidence is not None else None,
        is_confirmed=bool(ocr.is_confirmed) if ocr else False,
        confirmed_tags=_split_csv_tags(ocr.confirmed_tags if ocr else None),
    )


UPLOAD_RECORD_ID_OFFSET = 1_000_000_000


def _encode_uploaded_record_order_id(uploaded_record_id: int) -> int:
    return UPLOAD_RECORD_ID_OFFSET + uploaded_record_id


def _decode_uploaded_record_order_id(order_id: int) -> int | None:
    if order_id >= UPLOAD_RECORD_ID_OFFSET and order_id < 2_000_000_000:
        return order_id - UPLOAD_RECORD_ID_OFFSET
    return None

LIMS_RECORD_ID_OFFSET = 2_000_000_000

def _encode_lims_record_order_id(lims_record_id: int) -> int:
    return LIMS_RECORD_ID_OFFSET + lims_record_id

def _decode_lims_record_order_id(order_id: int) -> int | None:
    if order_id >= LIMS_RECORD_ID_OFFSET:
        return order_id - LIMS_RECORD_ID_OFFSET
    return None

def _normalize_uploaded_record_id(record_id: int) -> int:

    decoded = _decode_uploaded_record_order_id(record_id)
    return decoded if decoded is not None else record_id


def _record_date_sort_value(record: schemas.Record) -> datetime:
    raw = record.date
    if not raw:
        return datetime.min
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(raw), datetime.min.time())
        except ValueError:
            return datetime.min


def _to_uploaded_record_response(record: models.UploadedRecord) -> schemas.Record:
    confirmed_tags = _split_csv_tags(record.ocr_result.confirmed_tags) if record.ocr_result else []
    extracted_tags = _split_csv_tags(record.ocr_result.extracted_tags) if record.ocr_result else []
    tags = confirmed_tags or extracted_tags
    test_names = tags or ([record.title] if record.title else [record.file_name])
    source = record.source_facility or record.source_doctor or "Manual Upload"

    if record.issued_date:
        date_value = datetime.combine(record.issued_date, datetime.min.time()).isoformat()
    elif record.created_at:
        date_value = record.created_at.isoformat()
    else:
        date_value = datetime.now().isoformat()

    return schemas.Record(
        order_id=_encode_uploaded_record_order_id(record.id),
        display_id=f"UPL-{record.id}",
        date=date_value,
        lab_name=source,
        status=record.upload_status,
        test_names=test_names,
        metadata=schemas.RecordMetadata(
            record_type=record.record_type or "lab_report",
            source=source,
            source_type="lab",
            tags=tags,
        ),
    )


@app.get("/api/v1/profiles", response_model=list[schemas.ProfileSummary])
async def list_profiles(current_user: models.PhrUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # Sync with LIMS to discover any new dependent profiles
    try:
        lims_reports = await lims_client.get_lims_reports(current_user.contact_phone)
        if lims_reports:
            # Get existing profiles to avoid duplicates
            existing_profiles_result = await db.execute(
                select(models.Profile).where(models.Profile.owner_user_id == current_user.id)
            )
            existing_profiles = existing_profiles_result.scalars().all()
            existing_names = {p.full_name.lower().strip() for p in existing_profiles}
            
            # Find new names from LIMS
            new_profiles_to_create = []
            seen_names_in_lims = set()
            
            for report in lims_reports:
                name = report.get("patientName", "").strip()
                name_lower = name.lower()
                if name and name_lower not in existing_names and name_lower not in seen_names_in_lims:
                    seen_names_in_lims.add(name_lower)
                    # Create new profile
                    relationship = report.get("relationship", "other")
                    # If LIMS says relationship is "self" but we already have a primary, change it to "other"
                    if relationship == "self":
                        relationship = "other"
                        
                    new_profiles_to_create.append(
                        models.Profile(
                            owner_user_id=current_user.id,
                            full_name=name,
                            relationship_type=relationship,
                            is_primary=False,
                            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                        )
                    )
            
            if new_profiles_to_create:
                db.add_all(new_profiles_to_create)
                await db.commit()
                logger.info(f"Auto-created {len(new_profiles_to_create)} profiles from LIMS for {current_user.contact_phone}")
    except Exception as e:
        logger.error(f"Error syncing LIMS profiles: {str(e)}")

    profiles = await crud.list_accessible_profiles(db, current_user)
    return [_to_profile_summary(p) for p in profiles]


@app.get("/api/v1/profiles/{profile_id}", response_model=schemas.ProfileSummary)
async def get_profile(
    profile_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await crud.get_profile_if_accessible(db, profile_id, current_user)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
        )

    return _to_profile_summary(profile)


@app.post("/api/v1/profiles", response_model=schemas.ProfileSummary, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: schemas.ProfileCreateRequest,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await crud.create_profile(db, current_user, payload)
    return _to_profile_summary(profile)


@app.put("/api/v1/profiles/{profile_id}", response_model=schemas.ProfileSummary)
async def update_profile(
    profile_id: int,
    payload: schemas.ProfileUpdateRequest,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await crud.get_profile_if_accessible(db, profile_id, current_user)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
        )

    can_edit = await crud.can_edit_profile(db, profile, current_user)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PROFILE_EDIT_FORBIDDEN", "message": "You are not allowed to edit this profile"},
        )

    updated = await crud.update_profile(db, profile, payload)
    return _to_profile_summary(updated)


@app.delete("/api/v1/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await crud.get_profile_if_accessible(db, profile_id, current_user)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
        )

    if profile.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PROFILE_DELETE_FORBIDDEN", "message": "Only the owner can delete this profile"},
        )

    if profile.is_primary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PRIMARY_PROFILE_DELETE_FORBIDDEN", "message": "Primary profile cannot be deleted"},
        )

    await crud.delete_profile(db, profile)
    return None


@app.get("/api/v1/profiles/{profile_id}/caregivers", response_model=list[schemas.CaregiverPermissionResponse])
async def list_profile_caregivers(
    profile_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await crud.get_profile_if_accessible(db, profile_id, current_user)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
        )

    if profile.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CAREGIVER_VIEW_FORBIDDEN", "message": "Only owner can view caregiver assignments"},
        )

    permissions = await crud.list_caregiver_permissions(db, profile)
    return [_to_caregiver_permission_response(p) for p in permissions]


@app.post(
    "/api/v1/profiles/{profile_id}/caregivers",
    response_model=schemas.CaregiverPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_profile_caregiver(
    profile_id: int,
    payload: schemas.CaregiverGrantRequest,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await crud.get_profile_if_accessible(db, profile_id, current_user)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
        )

    if profile.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CAREGIVER_ASSIGN_FORBIDDEN", "message": "Only owner can assign caregivers"},
        )

    caregiver_user = await crud.get_user_by_phone(db, payload.caregiver_user_phone)
    if not caregiver_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CAREGIVER_USER_NOT_FOUND", "message": "Caregiver user not found"},
        )

    permission = await crud.grant_caregiver_permission(
        db,
        profile=profile,
        caregiver_user=caregiver_user,
        can_view=payload.can_view,
        can_edit=payload.can_edit,
    )
    return _to_caregiver_permission_response(permission)


@app.delete("/api/v1/profiles/{profile_id}/caregivers/{caregiver_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_profile_caregiver(
    profile_id: int,
    caregiver_user_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await crud.get_profile_if_accessible(db, profile_id, current_user)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
        )

    if profile.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CAREGIVER_REVOKE_FORBIDDEN", "message": "Only owner can revoke caregivers"},
        )

    revoked = await crud.revoke_caregiver_permission(db, profile, caregiver_user_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CAREGIVER_ASSIGNMENT_NOT_FOUND", "message": "Caregiver assignment not found"},
        )

    return None


@app.get("/api/v1/records", response_model=schemas.RecordListResponse)
async def read_records(
    search: str | None = None,
    record_status: str | None = Query(default=None, alias="status"),
    record_type: str | None = None,
    source: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="date"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Find patient by phone number
    patient = await crud.get_patient_by_phone(db, phone_number=current_user.contact_phone)
    if not patient:
        # Return empty list payload if no patient record found
        logger.info(f"No patient record found for phone: {current_user.contact_phone}")
        return schemas.RecordListResponse(items=[], total=0, page=page, page_size=page_size, total_pages=0)
    
    records_data, total = await crud.get_records(
        db,
        patient_id=patient.id,
        search=search,
        status=record_status,
        record_type=record_type,
        source=source,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    items = [
        schemas.Record(
            order_id=r.id,
            display_id=r.local_order_value,
            date=r.order_date.isoformat(),
            lab_name=r.organization_name,
            status=r.status,
            test_names=r.test_names,
            metadata=schemas.RecordMetadata(
                record_type=r.record_type,
                source=r.organization_name,
                source_type="lab",
                tags=r.test_names,
            ),
        )
        for r in records_data
    ]
    total_pages = (total + page_size - 1) // page_size if total else 0
    return schemas.RecordListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.get("/api/v1/records/profile/{profile_id}", response_model=schemas.RecordListResponse)
async def read_records_by_profile(
    profile_id: int,
    record_type: str | None = None,
    search: str | None = None,
    record_status: str | None = Query(default=None, alias="status"),
    source: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="date"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await crud.get_profile_if_accessible(db, profile_id, current_user)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
        )

    # Include uploaded records that are explicitly tied to the selected profile
    uploaded_query = (
        select(models.UploadedRecord)
        .options(selectinload(models.UploadedRecord.ocr_result))
        .where(models.UploadedRecord.profile_id == profile.id)
    )
    if record_type:
        uploaded_query = uploaded_query.where(models.UploadedRecord.record_type == record_type)
    if search:
        search_pattern = f"%{search}%"
        uploaded_query = uploaded_query.where(
            (models.UploadedRecord.title.ilike(search_pattern))
            | (models.UploadedRecord.file_name.ilike(search_pattern))
            | (models.UploadedRecord.source_facility.ilike(search_pattern))
            | (models.UploadedRecord.source_doctor.ilike(search_pattern))
        )
    if source:
        uploaded_query = uploaded_query.where(models.UploadedRecord.source_facility.ilike(f"%{source}%"))
    if from_date:
        uploaded_query = uploaded_query.where(models.UploadedRecord.created_at >= from_date)
    if to_date:
        uploaded_query = uploaded_query.where(models.UploadedRecord.created_at <= to_date)

    uploaded_result = await db.execute(uploaded_query)
    uploaded_records = uploaded_result.scalars().all()
    if record_status:
        normalized_status = record_status.lower()
        uploaded_records = [r for r in uploaded_records if (r.upload_status or "").lower() == normalized_status]

    uploaded_items = [_to_uploaded_record_response(r) for r in uploaded_records]

    # Merge lab service records (LIMS)
    legacy_items: list[schemas.Record] = []
    if True: # Now enabled for all profiles
        owner_result = await db.execute(select(models.PhrUser).where(models.PhrUser.id == profile.owner_user_id))
        owner_user = owner_result.scalars().first()
        if owner_user:
            patient = await crud.get_patient_by_phone(db, phone_number=owner_user.contact_phone)
            if patient:
                legacy_records, _ = await crud.get_records(
                    db,
                    patient_id=patient.id,
                    search=search,
                    status=record_status,
                    record_type=record_type,
                    source=source,
                    from_date=from_date,
                    to_date=to_date,
                    page=1,
                    page_size=1000,
                    sort_by="date",
                    sort_order="desc",
                )
                legacy_items = [
                    schemas.Record(
                        order_id=r.id,
                        display_id=r.local_order_value,
                        date=r.order_date.isoformat(),
                        lab_name=r.organization_name,
                        status=r.status,
                        test_names=r.test_names,
                        metadata=schemas.RecordMetadata(
                            record_type=r.record_type,
                            source=r.organization_name,
                            source_type="lab",
                            tags=r.test_names,
                        ),
                    )
                    for r in legacy_records
                ]

        # Fetch and merge linked laboratory records from LIMS for this specific profile
        lims_items: list[schemas.Record] = []
        try:
            # We fetch all reports for the mobile number, but filter for this profile's name
            lims_reports = await lims_client.get_lims_reports(owner_user.contact_phone)
            profile_name_lower = profile.full_name.lower().strip()
            
            lims_items = [
                schemas.Record(
                    order_id=_encode_lims_record_order_id(r["serviceRequestId"]),
                    display_id=r["localOrderValue"],
                    date=r["createdAt"],
                    lab_name="LIMS Laboratory",
                    status=r["status"],
                    test_names=r["tests"],
                    metadata=schemas.RecordMetadata(
                        record_type="lab_report",
                        source="lims",
                        source_type="lab",
                        tags=r["tests"],
                    ),
                )
                for r in lims_reports
                if r.get("patientName", "").lower().strip() == profile_name_lower
            ]
            if lims_items:
                logger.info(f"Merged {len(lims_items)} reports from LIMS for profile {profile.full_name}")
        except Exception as e:
            logger.error(f"Error merging LIMS reports for profile {profile_id}: {str(e)}")

    merged_items = legacy_items + uploaded_items + lims_items


    sort_field = (sort_by or "date").lower()
    descending = (sort_order or "desc").lower() == "desc"

    def _sort_key(item: schemas.Record):
        if sort_field == "display_id":
            return ((item.display_id or "").lower(), item.order_id)
        if sort_field == "status":
            return ((item.status or "").lower(), item.order_id)
        if sort_field == "source":
            return ((item.lab_name or "").lower(), item.order_id)
        if sort_field == "type":
            return ((item.metadata.record_type or "").lower(), item.order_id)
        return (_record_date_sort_value(item), item.order_id)

    merged_items = sorted(merged_items, key=_sort_key, reverse=descending)

    total = len(merged_items)
    safe_page = max(1, page)
    safe_page_size = min(max(1, page_size), 100)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    paginated = merged_items[start:end]
    total_pages = (total + safe_page_size - 1) // safe_page_size if total else 0

    return schemas.RecordListResponse(
        items=paginated,
        total=total,
        page=safe_page,
        page_size=safe_page_size,
        total_pages=total_pages,
    )


@app.post("/api/v1/records/upload")
async def upload_record(
    profile_id: int = Form(...),
    record_type: str = Form("lab_report"),
    title: str = Form(...),
    description: str | None = Form(None),
    issued_date: str | None = Form(None),
    source_facility: str | None = Form(None),
    source_doctor: str | None = Form(None),
    file: UploadFile = File(...),
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_types = {"application/pdf", "image/jpeg", "image/png", "image/jpg", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILE_TYPE", "message": "Only PDF and image files are supported"},
        )

    profile = await crud.get_profile_if_accessible(db, profile_id, current_user)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Profile not found"},
        )

    can_edit = await crud.can_edit_profile(db, profile, current_user)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PROFILE_EDIT_FORBIDDEN", "message": "You are not allowed to upload to this profile"},
        )

    stored_file = record_storage.save_upload(file, owner_user_id=profile.owner_user_id, profile_id=profile.id)

    parsed_date = infer_issued_date(issued_date)
    saved_record = await crud.create_uploaded_record(
        db,
        profile=profile,
        owner_user=current_user,
        record_type=record_type,
        title=title.strip(),
        description=description.strip() if description else None,
        issued_date=parsed_date,
        source_facility=source_facility.strip() if source_facility else None,
        source_doctor=source_doctor.strip() if source_doctor else None,
        file_name=stored_file.original_filename,
        file_path=stored_file.relative_path,
        mime_type=stored_file.content_type,
        file_size_bytes=stored_file.size_bytes,
    )

    return schemas.UploadRecordResponse(
        record_id=saved_record.id,
        profile_id=saved_record.profile_id,
        upload_status=saved_record.upload_status,
        file_name=saved_record.file_name,
        file_size_bytes=saved_record.file_size_bytes,
        ocr_status="pending",
    )


# from weasyprint import HTML  # Commented out - requires GTK libraries on Windows
import io

templates = Jinja2Templates(directory=f"{os.path.dirname(__file__)}/templates")


@app.get("/api/v1/records/{record_id}", response_model=schemas.RecordDetails)
async def read_record_details(
    record_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    encoded_uploaded_id = _decode_uploaded_record_order_id(record_id)
    if encoded_uploaded_id is not None:
        uploaded_record = await crud.get_uploaded_record_if_accessible(db, encoded_uploaded_id, current_user)
        if not uploaded_record:
            raise HTTPException(status_code=404, detail="Record not found")

        source = uploaded_record.source_facility or uploaded_record.source_doctor or "Manual Upload"
        confirmed_tags = _split_csv_tags(uploaded_record.ocr_result.confirmed_tags) if uploaded_record.ocr_result else []
        extracted_tags = _split_csv_tags(uploaded_record.ocr_result.extracted_tags) if uploaded_record.ocr_result else []
        tags = confirmed_tags or extracted_tags
        test_names = tags or ([uploaded_record.title] if uploaded_record.title else [uploaded_record.file_name])
        date_value = (
            datetime.combine(uploaded_record.issued_date, datetime.min.time()).isoformat()
            if uploaded_record.issued_date
            else uploaded_record.created_at.isoformat()
        )

        return schemas.RecordDetails(
            order_details=schemas.Record(
                order_id=record_id,
                display_id=f"UPL-{uploaded_record.id}",
                date=date_value,
                lab_name=source,
                status=uploaded_record.upload_status,
                test_names=test_names,
                metadata=schemas.RecordMetadata(
                    record_type=uploaded_record.record_type or "lab_report",
                    source=source,
                    source_type="lab",
                    tags=tags,
                ),
            ),
            analytes=[],
        )

    encoded_lims_id = _decode_lims_record_order_id(record_id)
    if encoded_lims_id is not None:
        lims_details = await lims_client.get_lims_report_details(encoded_lims_id, current_user.contact_phone)
        if not lims_details:
            raise HTTPException(status_code=404, detail="LIMS record not found")

        return schemas.RecordDetails(
            order_details=schemas.Record(
                order_id=record_id,
                display_id=lims_details["localOrderValue"],
                date=lims_details["createdAt"],
                lab_name=lims_details.get("labName", "LIMS Laboratory"),
                status=lims_details["status"],
                test_names=lims_details.get("tests", []),
                metadata=schemas.RecordMetadata(
                    record_type="lab_report",
                    source="lims",
                    source_type="lab",
                    tags=lims_details.get("tests", []),
                ),
            ),
            analytes=[
                schemas.Analyte(
                    name=a["name"],
                    result=a["result"] or "",
                    unit=a["unit"] or "",
                    reference_range=a["referenceRange"] or "",
                    status_color=a["statusColor"] or "GREEN",
                    method="",
                )
                for a in lims_details.get("analytes", [])
            ],
        )

    # Find patient by phone number

    patient = await crud.get_patient_by_phone(db, phone_number=current_user.contact_phone)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found")
    
    record_details = await crud.get_record_details(
        db, record_id=record_id, patient_id=patient.id
    )
    if record_details is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record_details


from fastapi.responses import FileResponse

@app.get("/api/v1/records/{record_id}/download")
async def download_record_file(
    record_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    encoded_uploaded_id = _decode_uploaded_record_order_id(record_id)
    if not encoded_uploaded_id:
        raise HTTPException(status_code=400, detail="Cannot download original file for this type of record")
        
    uploaded_record = await crud.get_uploaded_record_if_accessible(db, encoded_uploaded_id, current_user)
    if not uploaded_record:
        raise HTTPException(status_code=404, detail="Record not found")

    file_path = uploaded_record.file_path
    if hasattr(record_storage, "base_dir"):
        file_path = os.path.join(record_storage.base_dir, file_path)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    return FileResponse(
        path=file_path,
        filename=uploaded_record.file_name,
        media_type=uploaded_record.mime_type or "application/octet-stream"
    )


@app.get("/api/v1/records/{record_id}/download-legacy")
async def download_report(
    record_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Find patient by phone number
    patient = await crud.get_patient_by_phone(db, phone_number=current_user.contact_phone)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found")
    
    record_details = await crud.get_record_details(
        db, record_id=record_id, patient_id=patient.id
    )
    if record_details is None:
        raise HTTPException(status_code=404, detail="Record not found")

    patient = record_details.order_details.patient
    organization = record_details.order_details.encounter.organization
    practitioner = record_details.order_details.requester
    template_context = {
        "request": {},
        "lab_name": organization.organization_name,
        "lab_address": organization.address_line1,
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "patient_age": (datetime.now().date() - patient.date_of_birth).days // 365,
        "patient_gender": patient.gender,
        "order_id": record_details.order_details.display_id,
        "order_date": record_details.order_details.date,
        "doctor_name": f"{practitioner.first_name} {practitioner.last_name}",
        "analytes": record_details.analytes,
    }

    html_content = templates.get_template("report.html").render(template_context)
    # PDF generation disabled - requires GTK libraries on Windows
    # pdf_bytes = HTML(string=html_content).write_pdf()
    
    # Return HTML instead for now
    return HTMLResponse(content=html_content)

# MVP scope keeps auth, profiles, records, OCR, and linked LIMS endpoints.


@app.post("/api/v1/ocr/extract/{record_id}")
async def extract_ocr(
    record_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = await crud.get_uploaded_record_if_accessible(db, _normalize_uploaded_record_id(record_id), current_user)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_RECORD_NOT_FOUND", "message": "Uploaded record not found"},
        )

    can_edit = await crud.can_edit_profile(db, record.profile, current_user)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "OCR_EXTRACT_FORBIDDEN", "message": "You are not allowed to run OCR for this record"},
        )

    await crud.mark_ocr_processing(db, record)

    extracted_type = infer_record_type(record.file_name, declared=record.record_type)
    extracted_title = record.title or record.file_name
    extracted_tags = infer_tags(record.title, record.file_name)
    extracted_date = record.issued_date or infer_issued_date(record.file_name)
    extracted_source_facility = record.source_facility
    extracted_source_doctor = record.source_doctor

    completed = await crud.complete_ocr_extraction(
        db,
        record,
        extracted_record_type=extracted_type,
        extracted_title=extracted_title,
        extracted_issued_date=extracted_date,
        extracted_source_facility=extracted_source_facility,
        extracted_source_doctor=extracted_source_doctor,
        extracted_tags=extracted_tags,
        confidence=0.85,
        raw_text=f"Simulated OCR text for {record.file_name}",
    )

    return _to_ocr_response(completed)


@app.get("/api/v1/ocr/{record_id}")
async def get_ocr_status(
    record_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = await crud.get_uploaded_record_if_accessible(db, _normalize_uploaded_record_id(record_id), current_user)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_RECORD_NOT_FOUND", "message": "Uploaded record not found"},
        )
    return _to_ocr_response(record)


@app.post("/api/v1/ocr/{record_id}/confirm", response_model=schemas.OCRExtractionResponse)
async def confirm_ocr_tags(
    record_id: int,
    payload: schemas.OCRConfirmRequest,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = await crud.get_uploaded_record_if_accessible(db, _normalize_uploaded_record_id(record_id), current_user)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_RECORD_NOT_FOUND", "message": "Uploaded record not found"},
        )

    can_edit = await crud.can_edit_profile(db, record.profile, current_user)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "OCR_CONFIRM_FORBIDDEN", "message": "You are not allowed to confirm OCR tags for this record"},
        )

    updated = await crud.confirm_ocr_tags(db, record, payload)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "OCR_NOT_AVAILABLE", "message": "OCR extraction is not available for this record"},
        )

    return _to_ocr_response(updated)

    # return StreamingResponse(
    #     io.BytesIO(pdf_bytes),
    #     media_type="application/pdf",
    #     headers={"Content-Disposition": f"attachment; filename=report_{record_id}.pdf"},
    # )


# Part 6 — My Reports (Advanced Behavior)

@app.post("/api/v1/records/{record_id}/summary", response_model=schemas.ReportSummaryResponse)
async def summarize_report(
    record_id: int,
    request: Request,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a plain-language summary of a record"""
    request_id = request.state.request_id
    
    normalized_record_id = _normalize_uploaded_record_id(record_id)
    record = await crud.get_uploaded_record_if_accessible(db, normalized_record_id, current_user)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(request, "RECORD_NOT_FOUND", "Record not found or not accessible"),
        )
    
    summary = await crud.generate_report_summary(db, normalized_record_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_payload(request, "SUMMARY_GENERATION_FAILED", "Unable to generate summary for this record"),
        )
    
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    
    return summary


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(value)
            return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc)
        except ValueError:
            return None


def _extract_numeric_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _extract_reference_bounds(reference_text: str | None) -> tuple[float | None, float | None]:
    if not reference_text:
        return None, None
    nums = re.findall(r"-?\d+(?:\.\d+)?", reference_text)
    if len(nums) < 2:
        return None, None
    try:
        return float(nums[0]), float(nums[1])
    except ValueError:
        return None, None


def _trend_direction_from_values(values: list[float]) -> str:
    if not values:
        return "stable"
    split_idx = max(1, len(values) // 3)
    first_avg = sum(values[:split_idx]) / split_idx
    last_avg = sum(values[-split_idx:]) / split_idx
    if last_avg < first_avg * 0.95:
        return "improving"
    if last_avg > first_avg * 1.05:
        return "worsening"
    return "stable"


def _map_lims_status_color(status_color: str | None) -> str:
    normalized = (status_color or "").upper()
    if normalized == "RED":
        return "high"
    if normalized == "AMBER":
        return "low"
    return "normal"


async def _build_lims_trend_data(reports: list[dict], analyte: str, days: int, mobile: str) -> dict | None:
    analyte_lower = analyte.strip().lower()
    if not analyte_lower:
        return None

    now = datetime.now(timezone.utc)
    start_at = now - timedelta(days=days)

    trend_points: list[dict] = []
    ref_low: float | None = None
    ref_high: float | None = None
    ref_unit: str | None = None

    sorted_reports = sorted(
        reports,
        key=lambda report: _parse_iso_datetime(report.get("createdAt")) or datetime.min.replace(tzinfo=timezone.utc),
    )

    for report in sorted_reports:
        created_at = _parse_iso_datetime(report.get("createdAt"))
        if not created_at or created_at < start_at:
            continue

        report_id = report.get("serviceRequestId")
        if report_id is None:
            continue

        details = await lims_client.get_lims_report_details(int(report_id), mobile)
        if not details:
            continue

        analytes = details.get("analytes") or []
        matched = None
        for item in analytes:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            normalized_name = name.lower()
            if analyte_lower == normalized_name or analyte_lower in normalized_name or normalized_name in analyte_lower:
                matched = item
                break

        if not matched:
            continue

        numeric_value = _extract_numeric_value(matched.get("result"))
        if numeric_value is None:
            continue

        unit = str(matched.get("unit") or "").strip() or "mg/dL"
        status = _map_lims_status_color(matched.get("statusColor"))

        low, high = _extract_reference_bounds(matched.get("referenceRange"))
        if ref_low is None and low is not None:
            ref_low = low
        if ref_high is None and high is not None:
            ref_high = high
        if not ref_unit:
            ref_unit = unit

        trend_points.append(
            {
                "date": created_at.date(),
                "value": numeric_value,
                "unit": unit,
                "status": status,
            }
        )

    if not trend_points:
        return None

    values = [point["value"] for point in trend_points]
    stats = {
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 2),
        "trend_direction": _trend_direction_from_values(values),
    }

    reference_range = None
    if ref_low is not None and ref_high is not None:
        reference_range = {
            "low": ref_low,
            "high": ref_high,
            "unit": ref_unit or "mg/dL",
        }

    return {
        "trend_data": trend_points,
        "statistics": stats,
        "reference_range": reference_range,
    }


@app.get("/api/v1/records/{record_id}/trends/{analyte}", response_model=schemas.TrendComparisonResponse)
async def get_analyte_trends(
    record_id: int,
    analyte: str,
    request: Request,
    days: int = 30,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get trend data for an analyte over time"""
    request_id = request.state.request_id

    if days < 1 or days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_payload(request, "INVALID_DAYS", "Days must be between 1 and 365"),
        )

    encoded_lims_id = _decode_lims_record_order_id(record_id)
    if encoded_lims_id is not None:
        linked_reports = await lims_client.get_lims_reports(current_user.contact_phone)
        owns_selected_report = any(
            int(report.get("serviceRequestId", -1)) == encoded_lims_id
            for report in linked_reports
        )
        if not owns_selected_report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_payload(request, "RECORD_NOT_FOUND", "Record not found or not accessible"),
            )

        trend_data = await _build_lims_trend_data(linked_reports, analyte, days, current_user.contact_phone)
        if not trend_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_payload(request, "NO_TREND_DATA", f"No trend data found for analyte '{analyte}'"),
            )

        profile = await crud.ensure_primary_profile(db, current_user)
        return {
            "profile_id": profile.id,
            "analyte": analyte,
            **trend_data,
        }
    
    normalized_record_id = _normalize_uploaded_record_id(record_id)
    record = await crud.get_uploaded_record_if_accessible(db, normalized_record_id, current_user)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(request, "RECORD_NOT_FOUND", "Record not found or not accessible"),
        )
    
    trend_data = await crud.generate_trend_data(db, record.profile_id, analyte, days)
    if not trend_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(request, "NO_TREND_DATA", f"No trend data found for analyte '{analyte}'"),
        )
    
    return {
        "profile_id": record.profile_id,
        "analyte": analyte,
        **trend_data,
    }


def _build_lims_download_context(lims_details: dict, record_id: int) -> dict:
    tests = lims_details.get("tests") or []
    analytes = []

    for analyte in lims_details.get("analytes", []):
        status_color = str(analyte.get("statusColor") or "GREEN").upper()
        if status_color == "RED":
            status = "high"
        elif status_color == "AMBER":
            status = "low"
        else:
            status = "normal"

        analytes.append(
            {
                "analyte": analyte.get("name") or "Unknown",
                "value": analyte.get("result") or "",
                "unit": analyte.get("unit") or "",
                "status": status,
                "clinical_note": analyte.get("referenceRange") or "",
            }
        )

    report_title = lims_details.get("localOrderValue") or f"Report {record_id}"
    lab_name = lims_details.get("labName") or "LIMS Laboratory"
    patient_name = lims_details.get("patientName") or "Patient"

    return {
        "patient_name": patient_name,
        "generated_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "record_type": "lab_report",
        "title": report_title,
        "record_date": lims_details.get("createdAt") or "N/A",
        "facility": lab_name,
        "doctor": lims_details.get("requesterName") or lims_details.get("doctorName") or "Not specified",
        "summary_text": (
            f"This laboratory report contains results for {', '.join(tests) if tests else 'the ordered tests'} "
            f"from {lab_name}."
        ),
        "key_findings": analytes,
        "clinical_significance": (
            "Review the listed analytes alongside the ordering clinician's interpretation and the patient's "
            "clinical context. Values highlighted as abnormal may require follow-up."
        ),
        "disclaimer": (
            "This copy is provided for convenience and does not replace the original laboratory record or "
            "professional medical advice."
        ),
        "current_year": datetime.now().year,
    }


@app.get("/api/v1/records/{record_id}/download")
async def download_report_as_pdf(
    record_id: int,
    request: Request,
    format: Literal["html", "pdf"] = "html",
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download record as HTML or PDF"""
    request_id = request.state.request_id
    
    normalized_record_id = _normalize_uploaded_record_id(record_id)
    record = await crud.get_uploaded_record_if_accessible(db, normalized_record_id, current_user)
    context = None

    if record:
        summary = await crud.generate_report_summary(db, normalized_record_id)
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_error_payload(request, "DOWNLOAD_FAILED", "Unable to prepare record for download"),
            )

        context = {
            "patient_name": record.profile.full_name,
            "generated_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "record_type": record.record_type,
            "title": record.title,
            "record_date": str(record.issued_date or "N/A"),
            "facility": record.source_facility or "Not specified",
            "doctor": record.source_doctor or "Not specified",
            "summary_text": summary["summary_text"],
            "key_findings": summary["key_findings"],
            "clinical_significance": summary["clinical_significance"],
            "disclaimer": summary["disclaimer"],
            "current_year": datetime.now().year,
        }
    else:
        encoded_lims_id = _decode_lims_record_order_id(record_id)
        if encoded_lims_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_payload(request, "RECORD_NOT_FOUND", "Record not found or not accessible"),
            )

        lims_details = await lims_client.get_lims_report_details(encoded_lims_id, current_user.contact_phone)
        if not lims_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_payload(request, "RECORD_NOT_FOUND", "LIMS record not found or not accessible"),
            )

        context = _build_lims_download_context(lims_details, record_id)

    template = templates.get_template("report.html")
    html_content = template.render(**context)
    
    if format == "pdf":
        # Convert HTML to PDF using weasyprint
        try:
            from weasyprint import HTML, CSS
            from io import BytesIO
            
            pdf_bytes = HTML(string=html_content).write_pdf()
            
            return StreamingResponse(
                iter([pdf_bytes]),
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename=report_{record_id}.pdf"},
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_error_payload(
                    request,
                    "PDF_GENERATION_FAILED",
                    f"Failed to generate PDF: {str(e)}",
                ),
            )
    else:  # HTML
        return HTMLResponse(content=html_content)


@app.post("/api/v1/records/{record_id}/share", response_model=schemas.ShareLinkResponse)
async def create_share_link(
    record_id: int,
    request: Request,
    payload: schemas.ShareLinkCreateRequest,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a secure share link for a record"""
    request_id = request.state.request_id
    
    normalized_record_id = _normalize_uploaded_record_id(record_id)
    record = await crud.get_uploaded_record_if_accessible(db, normalized_record_id, current_user)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(request, "RECORD_NOT_FOUND", "Record not found or not accessible"),
        )
    
    # Must be owner to create share link
    if record.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_error_payload(request, "SHARE_FORBIDDEN", "You are not the owner of this record"),
        )
    
    share_link = await crud.create_share_link(
        db,
        record_id=record.id,
        owner_user_id=current_user.id,
        recipient_email=payload.recipient_email,
        access_duration_hours=payload.access_duration_hours,
    )
    
    # Generate shareable URL (frontend will construct the full URL)
    app_url = os.getenv("APP_URL", "https://phr.app")
    share_url = f"{app_url}/share/{share_link.token}"
    
    return {
        "share_token": share_link.token,
        "link": share_url,
        "expires_at": share_link.expires_at.isoformat(),
        "recipient_email": share_link.recipient_email,
    }


@app.get("/api/v1/records/{record_id}/share", response_model=list[schemas.ShareLinkSummary])
async def list_share_links(
    record_id: int,
    request: Request,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active share links for a record"""
    request_id = request.state.request_id
    
    normalized_record_id = _normalize_uploaded_record_id(record_id)
    record = await crud.get_uploaded_record_if_accessible(db, normalized_record_id, current_user)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(request, "RECORD_NOT_FOUND", "Record not found or not accessible"),
        )
    
    if record.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_error_payload(request, "LIST_FORBIDDEN", "You are not the owner of this record"),
        )
    
    links = await crud.list_share_links(db, record.id, current_user.id)
    
    return [
        {
            "id": link.id,
            "token": link.token,
            "recipient_email": link.recipient_email,
            "expires_at": link.expires_at.isoformat(),
            "is_revoked": link.is_revoked,
            "created_at": link.created_at.isoformat(),
        }
        for link in links
    ]


@app.delete("/api/v1/records/{record_id}/share/{token}")
async def revoke_share_link(
    record_id: int,
    token: str,
    request: Request,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a share link"""
    request_id = request.state.request_id
    
    normalized_record_id = _normalize_uploaded_record_id(record_id)
    record = await crud.get_uploaded_record_if_accessible(db, normalized_record_id, current_user)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(request, "RECORD_NOT_FOUND", "Record not found or not accessible"),
        )
    
    if record.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_error_payload(request, "REVOKE_FORBIDDEN", "You are not the owner of this record"),
        )
    
    success = await crud.revoke_share_link(db, record.id, token, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(request, "SHARE_LINK_NOT_FOUND", "Share link not found"),
        )
    
    return {"status": "ok"}


@app.get("/api/v1/share/{token}")
async def access_shared_report(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Access a report via public share link (no auth required)"""
    request_id = request.state.request_id
    
    share_link = await crud.get_share_link_by_token(db, token)
    if not share_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(request, "SHARE_LINK_EXPIRED_OR_REVOKED", "This share link is invalid, expired, or has been revoked"),
        )
    
    record = share_link.record
    summary = await crud.generate_report_summary(db, record.id)
    
    return {
        "record": {
            "id": record.id,
            "title": record.title,
            "record_type": record.record_type,
            "issued_date": record.issued_date,
            "source_facility": record.source_facility,
            "source_doctor": record.source_doctor,
        },
        "summary": summary,
        "shared_by": share_link.owner_user.contact_phone if share_link.owner_user else "Unknown",
        "expires_at": share_link.expires_at.isoformat(),
    }


