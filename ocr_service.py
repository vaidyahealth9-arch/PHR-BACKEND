from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from typing import Any


def infer_record_type(filename: str, declared: str | None = None) -> str:
    lowered = (declared or "").strip().lower()
    if lowered:
        return lowered

    name = filename.lower()
    if "prescription" in name or "rx" in name:
        return "prescription"
    if "xray" in name or "ct" in name or "mri" in name or "radiology" in name:
        return "radiology"
    return "lab_report"


def infer_record_type_from_text(raw_text: str, fallback_filename: str, declared: str | None = None) -> str:
    lowered = (declared or "").strip().lower()
    if lowered:
        return lowered

    text = (raw_text or "").lower()
    if any(token in text for token in ["prescription", "rx", "tablet", "capsule", "dosage"]):
        return "prescription"
    if any(token in text for token in ["x-ray", "xray", "mri", "ct scan", "radiology", "ultrasound"]):
        return "radiology"
    if any(token in text for token in ["hemoglobin", "cbc", "glucose", "wbc", "platelet", "analyte"]):
        return "lab_report"
    return infer_record_type(fallback_filename, declared)


def infer_tags(title: str | None, filename: str) -> list[str]:
    text = f"{title or ''} {filename}".lower()
    candidates = [
        "cbc",
        "glucose",
        "thyroid",
        "lft",
        "kft",
        "xray",
        "mri",
        "ct",
        "prescription",
    ]
    tags = [token.upper() if len(token) <= 3 else token.title() for token in candidates if token in text]
    return tags or ["General"]


def infer_tags_from_text(title: str | None, filename: str, raw_text: str) -> list[str]:
    text = f"{title or ''} {filename} {raw_text or ''}".lower()
    candidates = [
        "cbc",
        "glucose",
        "hba1c",
        "thyroid",
        "tsh",
        "lft",
        "kft",
        "creatinine",
        "lipid",
        "xray",
        "mri",
        "ct",
        "prescription",
        "blood pressure",
    ]
    force_upper = {"hba1c", "tsh", "lft", "kft", "cbc", "ct", "mri"}
    mapped: list[str] = []
    for token in candidates:
        if token in text:
            if token in force_upper:
                mapped.append(token.upper())
            else:
                mapped.append(token.upper() if len(token) <= 3 else token.title())
    return list(dict.fromkeys(mapped)) or infer_tags(title, filename)


def infer_issued_date(raw: str | None) -> date | None:
    if not raw:
        return None

    patterns = [r"(\d{4}-\d{2}-\d{2})", r"(\d{2}/\d{2}/\d{4})"]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            value = match.group(1)
            try:
                if "/" in value:
                    day, month, year = value.split("/")
                    return date(int(year), int(month), int(day))
                return date.fromisoformat(value)
            except ValueError:
                return None

    return None


def infer_issued_date_from_text(raw_text: str | None) -> date | None:
    if not raw_text:
        return None

    direct_iso = infer_issued_date(raw_text)
    if direct_iso:
        return direct_iso

    patterns = [
        r"(?:date|dated|collected on|reported on)[:\s-]*([0-3]?\d[/-][0-1]?\d[/-]\d{4})",
        r"(?:date|dated|collected on|reported on)[:\s-]*(\d{4}[/-][0-1]?\d[/-][0-3]?\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            parsed = infer_issued_date(match.group(1))
            if parsed:
                return parsed
    return None


def infer_source_facility(raw_text: str | None) -> str | None:
    if not raw_text:
        return None
    patterns = [
        r"(?:hospital|lab|laboratory|diagnostics?)\s*[:\-]?\s*([A-Za-z0-9 .,&()-]{4,80})",
        r"^([A-Za-z0-9 .,&()-]{4,80}(?:hospital|lab|laboratory|diagnostics?))$",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip(" :-")
            if value:
                return value
    return None


def infer_source_doctor(raw_text: str | None) -> str | None:
    if not raw_text:
        return None
    pattern = r"(?:dr\.?|doctor)\s*[:\-]?\s*([A-Za-z .'-]{3,60})"
    match = re.search(pattern, raw_text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def _extract_pdf_text(file_path: Path) -> tuple[str, str]:
    # Preferred: pdfplumber
    try:
        import pdfplumber  # type: ignore

        chunks: list[str] = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks), "pdfplumber"
    except Exception:
        pass

    # Fallback: pypdf
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(file_path))
        chunks = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text)
        if chunks:
            return "\n".join(chunks), "pypdf"
    except Exception:
        pass

    return "", "none"


def _extract_image_text(file_path: Path) -> tuple[str, str]:
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore

        image = Image.open(str(file_path))
        text = pytesseract.image_to_string(image) or ""
        if text.strip():
            return text, "pytesseract"
    except Exception:
        pass
    return "", "none"


def extract_text_from_document(file_path: str, mime_type: str | None = None) -> tuple[str, str]:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return "", "none"

    normalized_mime = (mime_type or "").lower()
    suffix = path.suffix.lower()

    if normalized_mime == "application/pdf" or suffix == ".pdf":
        return _extract_pdf_text(path)

    if normalized_mime.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return _extract_image_text(path)

    return "", "none"


def build_ocr_artifacts(
    *,
    file_path: str,
    mime_type: str | None,
    filename: str,
    title: str | None,
    declared_record_type: str | None,
) -> dict[str, Any]:
    raw_text, engine = extract_text_from_document(file_path=file_path, mime_type=mime_type)

    extracted_record_type = infer_record_type_from_text(raw_text, filename, declared=declared_record_type)
    extracted_title = title or filename
    extracted_issued_date = infer_issued_date_from_text(raw_text) or infer_issued_date(filename)
    extracted_source_facility = infer_source_facility(raw_text)
    extracted_source_doctor = infer_source_doctor(raw_text)
    extracted_tags = infer_tags_from_text(title, filename, raw_text)

    if not raw_text.strip():
        confidence = 0.35
    elif len(raw_text) < 120:
        confidence = 0.55
    elif len(raw_text) < 500:
        confidence = 0.72
    else:
        confidence = 0.88

    return {
        "extracted_record_type": extracted_record_type,
        "extracted_title": extracted_title,
        "extracted_issued_date": extracted_issued_date,
        "extracted_source_facility": extracted_source_facility,
        "extracted_source_doctor": extracted_source_doctor,
        "extracted_tags": extracted_tags,
        "confidence": confidence,
        "raw_text": raw_text,
        "engine": engine,
    }
