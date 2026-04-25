from datetime import datetime, timedelta, timezone

from auth_lifecycle import AuthLifecycleManager, OTPPolicy


def test_otp_resend_cooldown_enforced():
    manager = AuthLifecycleManager(OTPPolicy(resend_cooldown_seconds=30))
    now = datetime.now(timezone.utc)

    manager.issue_otp("9990001111", "123456", now=now)
    allowed, error = manager.can_send_otp("9990001111", now=now + timedelta(seconds=10))

    assert allowed is False
    assert error
    assert error["code"] == "OTP_RESEND_COOLDOWN"


def test_otp_rate_limit_enforced():
    manager = AuthLifecycleManager(OTPPolicy(max_sends_per_hour=2, resend_cooldown_seconds=0))
    now = datetime.now(timezone.utc)

    manager.issue_otp("9990001111", "111111", now=now)
    manager.issue_otp("9990001111", "222222", now=now + timedelta(minutes=1))

    allowed, error = manager.can_send_otp("9990001111", now=now + timedelta(minutes=2))
    assert allowed is False
    assert error
    assert error["code"] == "OTP_RATE_LIMITED"


def test_otp_verification_lock_after_retries():
    manager = AuthLifecycleManager(OTPPolicy(max_verify_attempts=3, verification_lock_minutes=5))
    now = datetime.now(timezone.utc)

    manager.issue_otp("9990001111", "123456", now=now)

    ok, err = manager.verify_otp("9990001111", "000000", now=now)
    assert ok is False
    assert err and err["code"] == "INVALID_OTP"

    ok, err = manager.verify_otp("9990001111", "000000", now=now + timedelta(seconds=1))
    assert ok is False
    assert err and err["code"] == "INVALID_OTP"

    ok, err = manager.verify_otp("9990001111", "000000", now=now + timedelta(seconds=2))
    assert ok is False
    assert err and err["code"] == "OTP_VERIFICATION_LOCKED"


def test_token_revocation_set():
    manager = AuthLifecycleManager()
    jti = "token-jti-123"

    assert manager.is_token_revoked(jti) is False
    manager.revoke_token_jti(jti)
    assert manager.is_token_revoked(jti) is True
