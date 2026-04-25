import os
import logging

from integrations.internal_service_client import InternalServiceClient

logger = logging.getLogger(__name__)

def _default_lims_base_url() -> str:
    # If backend is running in Docker, localhost points to the backend container itself.
    # On Docker Desktop (Windows/macOS), host.docker.internal routes to the host machine.
    if os.path.exists("/.dockerenv"):
        return "http://lims-backend:8080"
    return "http://localhost:8080"


LIMS_LOCAL_BASE_URL = os.getenv("LIMS_SERVICE_URL", os.getenv("LIMS_BASE_URL", _default_lims_base_url()))
LIMS_CLOUD_BASE_URL = os.getenv("LIMS_SERVICE_URL_CLOUD", LIMS_LOCAL_BASE_URL)

_internal_client = InternalServiceClient(
    service_name="lims",
    local_base_url=LIMS_LOCAL_BASE_URL,
    cloud_base_url=LIMS_CLOUD_BASE_URL,
    timeout_seconds=12.0,
    max_retries=3,
    circuit_failure_threshold=5,
    circuit_cooldown_seconds=30,
)

async def get_lims_reports(mobile: str) -> list[dict]:
    logger.info("Fetching LIMS reports for mobile: %s", mobile)
    try:
        response = await _internal_client.request(
            method="GET",
            path="/api/integration/phr/reports",
            params={"mobile": mobile},
            timeout_seconds=10.0,
            user_mobile=mobile,
        )
        if response.status_code == 200:
            reports = response.json()
            logger.info("Successfully fetched %s reports from LIMS for %s", len(reports), mobile)
            return reports
        logger.error("LIMS reports fetch error: %s - %s", response.status_code, response.text)
        return []
    except Exception as e:
        logger.error("LIMS reports connection error: %s", str(e))
        return []


async def get_lims_bills(mobile: str) -> list[dict]:
    logger.info("Fetching LIMS bills for mobile: %s", mobile)
    try:
        response = await _internal_client.request(
            method="GET",
            path="/api/integration/phr/bills",
            params={"mobile": mobile},
            timeout_seconds=10.0,
            user_mobile=mobile,
        )
        if response.status_code == 200:
            bills = response.json()
            logger.info("Successfully fetched %s bills from LIMS for %s", len(bills), mobile)
            return bills
        logger.error("LIMS bills fetch error: %s - %s", response.status_code, response.text)
        return []
    except Exception as e:
        logger.error("LIMS bills connection error: %s", str(e))
        return []


async def get_lims_report_details(report_id: int, mobile: str) -> dict | None:
    logger.info("Fetching LIMS report details for ID: %s", report_id)
    try:
        response = await _internal_client.request(
            method="GET",
            path=f"/api/integration/phr/reports/{report_id}",
            params={"mobile": mobile},
            timeout_seconds=10.0,
            user_mobile=mobile,
        )
        if response.status_code == 200:
            logger.info("Successfully fetched LIMS report details for %s", report_id)
            return response.json()
        logger.error("LIMS report details fetch error: %s - %s", response.status_code, response.text)
        return None
    except Exception as e:
        logger.error("LIMS report details connection error: %s", str(e))
        return None


async def get_lims_report_pdf(
    report_id: int,
    mobile: str,
    report_type: str = "regular",
    with_header: bool = True,
) -> tuple[bytes, str] | None:
    logger.info("Fetching LIMS report PDF for ID: %s", report_id)
    try:
        response = await _internal_client.request(
            method="GET",
            path=f"/api/integration/phr/reports/{report_id}/pdf",
            params={
                "mobile": mobile,
                "reportType": report_type,
                "withHeader": str(with_header).lower(),
            },
            timeout_seconds=30.0,
            user_mobile=mobile,
        )
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "application/pdf")
            logger.info("Successfully fetched LIMS report PDF for %s", report_id)
            return response.content, content_type

        logger.error("LIMS report PDF fetch error: %s - %s", response.status_code, response.text)
        return None
    except Exception as e:
        logger.error("LIMS report PDF connection error: %s", str(e))
        return None

async def get_lims_analyte_history(mobile: str) -> dict | None:
    logger.info("Fetching LIMS analyte history for mobile: %s", mobile)
    try:
        response = await _internal_client.request(
            method="GET",
            path="/api/integration/phr/analyte-history",
            params={"mobile": mobile},
            timeout_seconds=15.0,
            user_mobile=mobile,
        )
        if response.status_code == 200:
            data = response.json()
            logger.info("Successfully fetched LIMS analyte history for %s", mobile)
            return data
        logger.error("LIMS analyte history fetch error: %s - %s", response.status_code, response.text)
        return None
    except Exception as e:
        logger.error("LIMS analyte history connection error: %s", str(e))
        return None
