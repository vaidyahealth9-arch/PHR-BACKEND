import pytest
from httpx import AsyncClient

import main


LIMS_RECORD_ID_OFFSET = 2_000_000_000


@pytest.mark.asyncio
async def test_lims_record_details_are_fetched_with_authenticated_users_mobile(
    client: AsyncClient,
    authenticated_user: dict,
    monkeypatch,
):
    captured: dict[str, object] = {}

    async def fake_get_lims_report_details(report_id: int, mobile: str):
        captured["report_id"] = report_id
        captured["mobile"] = mobile
        return {
            "serviceRequestId": report_id,
            "localOrderValue": "ORD-42",
            "createdAt": "2026-04-18T10:00:00+00:00",
            "status": "final",
            "labName": "Halo LIMS",
            "tests": ["CBC"],
            "analytes": [
                {
                    "name": "Hemoglobin",
                    "result": "13.5",
                    "unit": "g/dL",
                    "referenceRange": "12-16",
                    "statusColor": "GREEN",
                }
            ],
        }

    monkeypatch.setattr(main.lims_client, "get_lims_report_details", fake_get_lims_report_details)

    response = await client.get(
        f"/api/v1/records/{LIMS_RECORD_ID_OFFSET + 42}",
        headers=authenticated_user["headers"],
    )

    assert response.status_code == 200
    assert captured == {"report_id": 42, "mobile": authenticated_user["phone"]}
    assert response.json()["order_details"]["display_id"] == "ORD-42"


@pytest.mark.asyncio
async def test_lims_report_pdf_proxy_uses_authenticated_users_mobile(
    client: AsyncClient,
    authenticated_user: dict,
    monkeypatch,
):
    captured: dict[str, object] = {}

    async def fake_get_lims_report_pdf(
        report_id: int,
        mobile: str,
        report_type: str = "regular",
        with_header: bool = True,
    ):
        captured["report_id"] = report_id
        captured["mobile"] = mobile
        captured["report_type"] = report_type
        captured["with_header"] = with_header
        return (b"%PDF-1.4 test", "application/pdf")

    monkeypatch.setattr(main.lims_client, "get_lims_report_pdf", fake_get_lims_report_pdf)

    response = await client.get(
        "/api/v1/linked/lims/reports/42/pdf",
        headers=authenticated_user["headers"],
    )

    assert response.status_code == 200
    assert captured == {
        "report_id": 42,
        "mobile": authenticated_user["phone"],
        "report_type": "regular",
        "with_header": True,
    }
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 test"
