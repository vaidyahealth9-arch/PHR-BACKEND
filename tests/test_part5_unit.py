from pathlib import Path

from ocr_service import (
    build_ocr_artifacts,
    infer_issued_date,
    infer_issued_date_from_text,
    infer_record_type,
    infer_record_type_from_text,
    infer_tags,
    infer_tags_from_text,
)


def test_infer_record_type_prefers_declared_value():
    assert infer_record_type("scan.pdf", declared="radiology") == "radiology"


def test_infer_record_type_from_filename():
    assert infer_record_type("mri_brain_report.pdf") == "radiology"
    assert infer_record_type("rx_march.jpg") == "prescription"


def test_infer_tags_and_date():
    tags = infer_tags("CBC and Glucose report", "report_12_02_2026.pdf")
    assert "CBC" in tags
    assert "Glucose" in tags

    parsed = infer_issued_date("invoice_2026-02-12_report")
    assert parsed is not None
    assert parsed.isoformat() == "2026-02-12"


def test_infer_record_type_from_text_and_tags_from_text():
    text = "Prescription advised by Dr. Ravi for tablet use"
    assert infer_record_type_from_text(text, fallback_filename="file.pdf") == "prescription"

    tags = infer_tags_from_text("Report", "report.pdf", "HbA1c and glucose levels are high")
    assert "HBA1C" in tags
    assert "Glucose" in tags


def test_infer_issued_date_from_text_with_label():
    text = "Collected On: 14/03/2026"
    parsed = infer_issued_date_from_text(text)
    assert parsed is not None
    assert parsed.isoformat() == "2026-03-14"


def test_build_ocr_artifacts_graceful_when_no_engine(tmp_path: Path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("random plain text", encoding="utf-8")

    artifacts = build_ocr_artifacts(
        file_path=str(txt_file),
        mime_type="text/plain",
        filename="sample.txt",
        title="Sample",
        declared_record_type=None,
    )

    assert artifacts["engine"] == "none"
    assert artifacts["extracted_title"] == "Sample"
    assert artifacts["extracted_record_type"] in {"lab_report", "prescription", "radiology"}
