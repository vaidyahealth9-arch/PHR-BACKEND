from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import auth
import crud
import models
import schemas
from database import SessionLocal, engine
from whatsapp_service import send_otp_via_whatsapp, is_whatsapp_configured

import os
import random
import string
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS Configuration - Allow frontend to make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for OTPs (for demonstration purposes - not suitable for production)
otp_store = {}


@app.get("/")
def read_root():
    return {"message": "Welcome to the PHR Backend Service"}


# Dependency
async def get_db():
    async with SessionLocal() as db:
        yield db


@app.post("/api/v1/auth/send-otp", response_model=schemas.SendOTPRequest)
async def send_otp(request: schemas.SendOTPRequest, db: Session = Depends(get_db)):
    db_user = await crud.get_user_by_phone(db, phone_number=request.phone_number)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Generate random 6-digit OTP
    # For development: use fixed OTP 123456 for test user
    if request.phone_number == "9800122899" and os.getenv("ENVIRONMENT", "development") == "development":
        otp = "123456"  # Fixed OTP for test user in development
        logger.info(f"Using fixed OTP for test user: {request.phone_number}")
    else:
        otp = "".join(random.choices(string.digits, k=6))
    
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


from datetime import datetime
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt


@app.post("/api/v1/auth/verify-otp", response_model=schemas.Token)
async def verify_otp(request: schemas.VerifyOTPRequest, db: Session = Depends(get_db)):
    db_user = await crud.get_user_by_phone(db, phone_number=request.phone_number)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify OTP from the database
    if db_user.otp is None or db_user.otp != request.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

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
    return {"access_token": access_token, "token_type": "bearer"}


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        phone_number: str = payload.get("sub")
        if phone_number is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = await crud.get_user_by_phone(db, phone_number=phone_number)
    if user is None:
        raise credentials_exception
    return user


@app.get("/api/v1/auth/me", response_model=schemas.UserProfile)
async def get_current_user_profile(
    current_user: models.PhrUser = Depends(get_current_user),
):
    """Get the current logged-in user's profile"""
    # Calculate full name
    full_name = current_user.first_name or ""
    if current_user.middle_name:
        full_name = f"{full_name} {current_user.middle_name}".strip()
    if current_user.last_name:
        full_name = f"{full_name} {current_user.last_name}".strip()
    if not full_name:
        full_name = "User"
    
    # Calculate age from date of birth
    age = None
    if current_user.date_of_birth:
        today = datetime.now().date()
        age = today.year - current_user.date_of_birth.year
        # Adjust if birthday hasn't occurred yet this year
        if (today.month, today.day) < (current_user.date_of_birth.month, current_user.date_of_birth.day):
            age -= 1
    
    return schemas.UserProfile(
        id=current_user.id,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        middle_name=current_user.middle_name,
        gender=current_user.gender,
        date_of_birth=current_user.date_of_birth,
        contact_phone=current_user.contact_phone,
        contact_email=current_user.contact_email,
        address_line1=current_user.address_line1,
        address_line2=current_user.address_line2,
        city=current_user.city,
        state=current_user.state,
        postal_code=current_user.postal_code,
        country=current_user.country,
        abha_address=current_user.abha_address,
        abha_id=current_user.abha_id,
        full_name=full_name,
        age=age,
    )


@app.get("/api/v1/records", response_model=list[schemas.Record])
async def read_records(
    search: str | None = None,
    status: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    records_data = await crud.get_records(
        db,
        patient_id=current_user.patient_id,
        search=search,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )
    return [
        schemas.Record(
            order_id=r.id,
            display_id=r.local_order_value,
            date=r.order_date.isoformat(),
            lab_name=r.organization_name,
            status=r.status,
            test_names=r.test_names,
        )
        for r in records_data
    ]


from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
# from weasyprint import HTML  # Commented out - requires GTK libraries on Windows
from fastapi.responses import StreamingResponse
import io

import os

templates = Jinja2Templates(directory=f"{os.path.dirname(__file__)}/templates")


@app.get("/api/v1/records/{record_id}", response_model=schemas.RecordDetails)
async def read_record_details(
    record_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record_details = await crud.get_record_details(
        db, record_id=record_id, patient_id=current_user.patient_id
    )
    if record_details is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record_details


@app.get("/api/v1/records/{record_id}/download")
async def download_report(
    record_id: int,
    current_user: models.PhrUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record_details = await crud.get_record_details(
        db, record_id=record_id, patient_id=current_user.patient_id
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

    # return StreamingResponse(
    #     io.BytesIO(pdf_bytes),
    #     media_type="application/pdf",
    #     headers={"Content-Disposition": f"attachment; filename=report_{record_id}.pdf"},
    # )
