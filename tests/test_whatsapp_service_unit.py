import pytest

import whatsapp_service as ws


class _MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _MockAsyncClient:
    def __init__(self, response: _MockResponse | None = None, raise_timeout: bool = False, *args, **kwargs):
        self._response = response
        self._raise_timeout = raise_timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        if self._raise_timeout:
            raise ws.httpx.TimeoutException("timeout")
        return self._response


def test_is_whatsapp_configured_false_when_missing_credentials(monkeypatch):
    monkeypatch.setattr(ws, "WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setattr(ws, "WHATSAPP_PHONE_NUMBER_ID", "")

    assert ws.is_whatsapp_configured() is False


def test_is_whatsapp_configured_true_when_credentials_present(monkeypatch):
    monkeypatch.setattr(ws, "WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setattr(ws, "WHATSAPP_PHONE_NUMBER_ID", "phone-id")

    assert ws.is_whatsapp_configured() is True


@pytest.mark.asyncio
async def test_send_otp_via_whatsapp_returns_fallback_when_not_configured(monkeypatch):
    monkeypatch.setattr(ws, "WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setattr(ws, "WHATSAPP_PHONE_NUMBER_ID", "")

    result = await ws.send_otp_via_whatsapp("9800122899", "123456")

    assert result["success"] is False
    assert result["otp_logged"] is True
    assert "not configured" in result["message"].lower()


@pytest.mark.asyncio
async def test_send_otp_via_whatsapp_success_response(monkeypatch):
    monkeypatch.setattr(ws, "WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setattr(ws, "WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setattr(ws, "WHATSAPP_API_URL", "https://graph.facebook.com/v18.0/phone-id/messages")

    mock_response = _MockResponse(200, {"messages": [{"id": "wamid.123"}]})
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *args, **kwargs: _MockAsyncClient(response=mock_response))

    result = await ws.send_otp_via_whatsapp("9800122899", "123456")

    assert result["success"] is True
    assert result["message"] == "OTP sent via WhatsApp"
    assert result["message_id"] == "wamid.123"


@pytest.mark.asyncio
async def test_send_otp_via_whatsapp_handles_api_error(monkeypatch):
    monkeypatch.setattr(ws, "WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setattr(ws, "WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setattr(ws, "WHATSAPP_API_URL", "https://graph.facebook.com/v18.0/phone-id/messages")

    mock_response = _MockResponse(
        400,
        {"error": {"message": "Invalid recipient", "code": 131026}},
    )
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *args, **kwargs: _MockAsyncClient(response=mock_response))

    result = await ws.send_otp_via_whatsapp("9800122899", "123456")

    assert result["success"] is False
    assert "invalid recipient" in result["message"].lower()
    assert result["error_code"] == 131026


@pytest.mark.asyncio
async def test_send_otp_via_whatsapp_handles_timeout(monkeypatch):
    monkeypatch.setattr(ws, "WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setattr(ws, "WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setattr(ws, "WHATSAPP_API_URL", "https://graph.facebook.com/v18.0/phone-id/messages")
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda *args, **kwargs: _MockAsyncClient(raise_timeout=True))

    result = await ws.send_otp_via_whatsapp("9800122899", "123456")

    assert result["success"] is False
    assert "timed out" in result["message"].lower()
