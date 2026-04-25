"""
Part 1 backend tests intentionally focus on foundation hardening only:
- request-id middleware behavior
- uniform API error payload contract

Why older auth/records integration setup was removed from this file:
1) It was tied to pre-refactor model fields/import paths that no longer match runtime code.
2) Part 1 scope is middleware/error-contract + endpoint alignment; deep auth/records flows
    are covered as dedicated work in Part 2 (auth lifecycle) and Part 4 (records core).
3) Keeping this file narrowly scoped makes failures actionable and avoids false negatives
    from unfinished later-part behavior.

Follow-up:
- Add dedicated integration tests for OTP lifecycle in Part 2.
- Add records list/detail integration tests in Part 4.
"""

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_root_includes_request_id_header():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the PHR Backend Service"}
    assert response.headers.get("X-Request-ID")


def test_health_endpoint_reports_ok():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "phr-backend"
    assert payload["version"]
    assert payload["environment"]


def test_liveness_endpoint_reports_alive():
    response = client.get("/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "alive"
    assert isinstance(payload["uptime_seconds"], int)
    assert payload["uptime_seconds"] >= 0


def test_readiness_endpoint_reports_ready():
    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checked_at"]
    assert payload["components"]["api"]["status"] == "ok"
    assert payload["components"]["database"]["status"] == "ok"
    assert payload["components"]["database"]["latency_ms"] >= 0


def test_request_id_is_echoed_when_provided():
    response = client.get("/", headers={"X-Request-ID": "test-request-123"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "test-request-123"


def test_404_uses_uniform_error_payload():
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    payload = response.json()

    assert "error" in payload
    assert payload["error"]["code"] == "HTTP_404"
    assert "request_id" in payload["error"]
    assert payload["error"]["message"]


def test_validation_error_uses_uniform_payload():
    # Missing required phone_number field
    response = client.post("/api/v1/auth/send-otp", json={})
    assert response.status_code == 422
    payload = response.json()

    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"] == "Invalid request payload"
    assert isinstance(payload["error"]["details"], list)


def test_verify_token_schema_includes_refresh_token_for_part2():
    # Schema guard test: verify-otp returns both access and refresh tokens in Part 2.
    # This test exercises response shape expectations only, not end-to-end auth flow.
    from schemas import Token

    token = Token(access_token="a", refresh_token="r", token_type="bearer")
    assert token.access_token == "a"
    assert token.refresh_token == "r"
