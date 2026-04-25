import os
import random
import time
import logging
import asyncio

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token


logger = logging.getLogger(__name__)


class InternalServiceClient:
    """Internal HTTP client with env-aware auth, retry, and lightweight circuit breaker."""

    def __init__(
        self,
        service_name: str,
        local_base_url: str,
        cloud_base_url: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        circuit_failure_threshold: int = 5,
        circuit_cooldown_seconds: int = 30,
    ):
        self.service_name = service_name
        self.local_base_url = local_base_url.rstrip("/")
        self.cloud_base_url = cloud_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_cooldown_seconds = circuit_cooldown_seconds
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _is_production_auth(self) -> bool:
        auth_mode = os.getenv("INTERNAL_AUTH_MODE", "auto").strip().lower()
        environment = os.getenv("ENVIRONMENT", "development").strip().lower()
        if auth_mode == "oidc":
            return True
        if auth_mode == "local":
            return False
        return environment in {"prod", "production"}

    def _resolve_base_url(self) -> str:
        if self._is_production_auth() and self.cloud_base_url:
            return self.cloud_base_url
        return self.local_base_url

    def _is_circuit_open(self) -> bool:
        return time.monotonic() < self._circuit_open_until

    def _mark_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _mark_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.circuit_failure_threshold:
            self._circuit_open_until = time.monotonic() + self.circuit_cooldown_seconds
            logger.warning(
                "Circuit opened for %s for %ss after %s consecutive failures",
                self.service_name,
                self.circuit_cooldown_seconds,
                self._consecutive_failures,
            )

    @staticmethod
    def _should_retry_status(status_code: int) -> bool:
        return status_code in {408, 425, 429, 500, 502, 503, 504}

    @staticmethod
    def _retry_delay_seconds(attempt: int) -> float:
        backoff = 0.35 * (2 ** attempt)
        jitter = random.uniform(0.0, 0.2)
        return backoff + jitter

    def _build_auth_headers(self, user_mobile: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if user_mobile:
            headers["X-User-Mobile"] = user_mobile

        if self._is_production_auth():
            audience = self._resolve_base_url()
            token = google_id_token.fetch_id_token(google_requests.Request(), audience)
            headers["Authorization"] = f"Bearer {token}"
            return headers

        internal_secret = os.getenv("INTERNAL_SECRET_KEY", "").strip()
        if not internal_secret:
            raise RuntimeError("INTERNAL_SECRET_KEY must be set for local internal auth")

        headers["X-Internal-Secret"] = internal_secret
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        timeout_seconds: float | None = None,
        user_mobile: str | None = None,
    ) -> httpx.Response:
        if self._is_circuit_open():
            raise RuntimeError(f"Circuit breaker open for {self.service_name}")

        base_url = self._resolve_base_url()
        url = f"{base_url}/{path.lstrip('/')}"
        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                headers = self._build_auth_headers(user_mobile=user_mobile)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(method=method, url=url, headers=headers, params=params)

                if self._should_retry_status(response.status_code):
                    self._mark_failure()
                    if attempt < self.max_retries - 1:
                        delay = self._retry_delay_seconds(attempt)
                        logger.warning(
                            "Retrying %s %s after %s (attempt %s/%s)",
                            method,
                            url,
                            response.status_code,
                            attempt + 1,
                            self.max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue

                if response.status_code >= 400:
                    self._mark_failure()
                else:
                    self._mark_success()
                return response
            except (httpx.TimeoutException, httpx.TransportError, RuntimeError) as exc:
                last_error = exc
                self._mark_failure()
                if attempt < self.max_retries - 1:
                    delay = self._retry_delay_seconds(attempt)
                    logger.warning(
                        "Transient error calling %s %s: %s. Retrying (%s/%s)",
                        method,
                        url,
                        str(exc),
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError(f"Failed to call {self.service_name} at {url}")
