from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class OTPPolicy:
    otp_ttl_seconds: int = 300
    resend_cooldown_seconds: int = 30
    max_sends_per_hour: int = 5
    max_verify_attempts: int = 5
    verification_lock_minutes: int = 15


@dataclass
class OTPRecord:
    otp: Optional[str] = None
    expires_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    send_timestamps: list[datetime] = field(default_factory=list)
    failed_attempts: int = 0
    locked_until: Optional[datetime] = None


class AuthLifecycleManager:
    def __init__(self, policy: OTPPolicy | None = None):
        self.policy = policy or OTPPolicy()
        self.otp_records: dict[str, OTPRecord] = {}
        self.revoked_token_jti: set[str] = set()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _record(self, phone_number: str) -> OTPRecord:
        if phone_number not in self.otp_records:
            self.otp_records[phone_number] = OTPRecord()
        return self.otp_records[phone_number]

    def can_send_otp(self, phone_number: str, now: datetime | None = None) -> tuple[bool, dict | None]:
        current = now or self._now()
        record = self._record(phone_number)

        # enforce resend cooldown
        if record.sent_at is not None:
            retry_after = (record.sent_at + timedelta(seconds=self.policy.resend_cooldown_seconds) - current).total_seconds()
            if retry_after > 0:
                return (
                    False,
                    {
                        "code": "OTP_RESEND_COOLDOWN",
                        "message": "Please wait before requesting another OTP",
                        "details": {"retry_after_seconds": int(retry_after)},
                    },
                )

        # enforce sends-per-hour limit
        one_hour_ago = current - timedelta(hours=1)
        record.send_timestamps = [ts for ts in record.send_timestamps if ts >= one_hour_ago]
        if len(record.send_timestamps) >= self.policy.max_sends_per_hour:
            retry_after = (min(record.send_timestamps) + timedelta(hours=1) - current).total_seconds()
            return (
                False,
                {
                    "code": "OTP_RATE_LIMITED",
                    "message": "Too many OTP requests. Please try again later",
                    "details": {"retry_after_seconds": max(1, int(retry_after))},
                },
            )

        return True, None

    def issue_otp(self, phone_number: str, otp: str, now: datetime | None = None) -> OTPRecord:
        current = now or self._now()
        record = self._record(phone_number)

        record.otp = otp
        record.sent_at = current
        record.expires_at = current + timedelta(seconds=self.policy.otp_ttl_seconds)
        record.send_timestamps.append(current)
        record.failed_attempts = 0
        record.locked_until = None

        return record

    def verify_otp(self, phone_number: str, otp_input: str, now: datetime | None = None) -> tuple[bool, dict | None]:
        current = now or self._now()
        record = self._record(phone_number)

        if not record.otp:
            return (
                False,
                {
                    "code": "OTP_NOT_REQUESTED",
                    "message": "No active OTP found. Please request a new OTP",
                },
            )

        if record.locked_until and current < record.locked_until:
            retry_after = int((record.locked_until - current).total_seconds())
            return (
                False,
                {
                    "code": "OTP_VERIFICATION_LOCKED",
                    "message": "Too many invalid attempts. Try again later",
                    "details": {"retry_after_seconds": max(1, retry_after)},
                },
            )

        if record.expires_at and current > record.expires_at:
            return (
                False,
                {
                    "code": "OTP_EXPIRED",
                    "message": "OTP has expired. Please request a new OTP",
                },
            )

        if otp_input != record.otp:
            record.failed_attempts += 1
            remaining_attempts = self.policy.max_verify_attempts - record.failed_attempts

            if record.failed_attempts >= self.policy.max_verify_attempts:
                record.locked_until = current + timedelta(minutes=self.policy.verification_lock_minutes)
                return (
                    False,
                    {
                        "code": "OTP_VERIFICATION_LOCKED",
                        "message": "Too many invalid attempts. Try again later",
                        "details": {"retry_after_seconds": self.policy.verification_lock_minutes * 60},
                    },
                )

            return (
                False,
                {
                    "code": "INVALID_OTP",
                    "message": "Invalid OTP",
                    "details": {"remaining_attempts": remaining_attempts},
                },
            )

        # Success: consume OTP
        record.otp = None
        record.expires_at = None
        record.failed_attempts = 0
        record.locked_until = None

        return True, None

    def revoke_token_jti(self, jti: str | None) -> None:
        if jti:
            self.revoked_token_jti.add(jti)

    def is_token_revoked(self, jti: str | None) -> bool:
        return bool(jti and jti in self.revoked_token_jti)

    def reset(self) -> None:
        self.otp_records.clear()
        self.revoked_token_jti.clear()
